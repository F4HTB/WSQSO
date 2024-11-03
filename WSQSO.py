import sys, random, re, configparser, collections, time
import numpy as np
from scipy.signal import argrelextrema 
from scipy.signal import hilbert
from datetime import datetime
from PyQt6.QtWidgets import (
	QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
	QTextEdit, QVBoxLayout, QHBoxLayout, QFormLayout, QMenu, QGridLayout,
	QFrame, QCheckBox, QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QGroupBox, QMessageBox, QComboBox, 
	QProgressBar
)
from PyQt6.QtGui import QAction, QActionGroup, QPainter, QColor, QPen, QImage, QIcon, QPalette
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSysInfo
from PyQt6.QtMultimedia import QAudioInput, QAudioFormat, QMediaDevices, QAudioSource

class TimerWorker(QThread):
	# Signal to send updated time to the main thread
	time_signal = pyqtSignal(int)

	def run(self):
		while True:
			now = datetime.now()
			ms_to_next_second = 1 - now.microsecond / 1_000_000.0
			time.sleep(ms_to_next_second)
			self.update_timer()

	def update_timer(self):
		now = datetime.now()
		total_seconds = (now.minute % 2) * 60 + now.second
		seconds_since_last_even_minute = total_seconds % 200
		# Emit the signal with the updated timer value
		self.time_signal.emit(seconds_since_last_even_minute)

class FrequencyScaleWidget(QWidget):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setMinimumWidth(50)  # Définir une largeur minimale pour l'échelle
		self.shift_frequency = None  # Fréquence de décalage à afficher

	def set_shift_frequency(self, frequency):
		"""Met à jour la valeur de la shift frequency et force la mise à jour de l'affichage."""
		min_freq = 1300
		max_freq = 1700

		# Assurez-vous que la fréquence est dans les limites de l'échelle
		if frequency < min_freq:
			frequency = min_freq
		elif frequency > max_freq:
			frequency = max_freq

		self.shift_frequency = frequency
		self.update()

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		painter.setPen(QPen(Qt.GlobalColor.black))  # Définir la couleur des traits en noir

		# Taille du widget pour adapter la position des traits
		widget_height = self.height()

		# Limites des fréquences du spectre affiché (1300 à 1700 Hz)
		min_freq = 1300
		max_freq = 1700

		# Pas de 50 Hz pour dessiner les traits
		frequency_step = 50

		# Dessiner les traits tous les 50 Hz
		for frequency in range(min_freq, max_freq + 1, frequency_step):
			# Calculer la position verticale correspondante sur le widget
			y = widget_height - ((frequency - min_freq) / (max_freq - min_freq) * widget_height)

			# Dessiner le trait (ligne)
			painter.drawLine(0, int(y), 10, int(y))

		# Dessiner les labels spécifiques pour 1400 Hz et 1600 Hz
		for frequency in [1400, 1600]:
			# Calculer la position verticale correspondante sur le widget
			y = widget_height - ((frequency - min_freq) / (max_freq - min_freq) * widget_height)

			# Dessiner le trait pour la fréquence spécifique
			painter.drawLine(0, int(y), 10, int(y))

			# Dessiner l'étiquette de la fréquence (label)
			painter.drawText(15, int(y + 5), f"{int(frequency)} Hz")

		# Dessiner le point rouge représentant la shift frequency, si elle est définie
		if self.shift_frequency is not None:
			# Calculer la position verticale du point rouge
			y_shift = widget_height - ((self.shift_frequency - min_freq) / (max_freq - min_freq) * widget_height)

			# Définir le pinceau pour dessiner en rouge
			painter.setPen(QPen(Qt.GlobalColor.red))
			painter.setBrush(Qt.GlobalColor.red)

			# Dessiner un petit cercle rouge représentant la shift frequency
			painter.drawEllipse(0, int(y_shift) - 5, 15, 4)  # Position et taille du cercle


class WaterfallCanvas(QWidget):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.spectrogram_height = 548
		self.spectrogram_width = 400
		self.image = QImage(self.spectrogram_width, self.spectrogram_height, QImage.Format.Format_RGB32)
		self.image.fill(Qt.GlobalColor.black)  # Remplir l'image avec du noir au démarrage
		self.update()  # Forcer la mise à jour pour afficher le fond noir
		self.should_draw_marker = False

	def update_data(self, new_data):
		# Convertir les nouvelles données FFT en intensités de couleur
		normalized_data = np.interp(new_data, (0, np.max(new_data)), (0, 255))
		# Décaler les colonnes existantes vers la gauche
		temp_image = QImage(self.image)
		painter = QPainter(self.image)
		# Copier les colonnes depuis la deuxième colonne jusqu'à la dernière, vers la première colonne
		painter.drawImage(0, 0, temp_image, 1, 0, self.spectrogram_width - 1, self.spectrogram_height)

		# Ajouter une nouvelle colonne à droite de l'image
		if len(normalized_data) > self.spectrogram_height:
			normalized_data = normalized_data[:self.spectrogram_height]  # S'assurer que les nouvelles données ne dépassent pas la hauteur

		# Inverser l'indexation de `y` pour que les fréquences basses soient en bas
		for y, value in enumerate(reversed(normalized_data)):
			intensity = int(value)
			color = QColor(intensity, intensity, 255 - intensity)  # Couleur bleue dégradée
			self.image.setPixel(self.spectrogram_width - 1, y, color.rgb())

		if self.should_draw_marker:
			# Définir le style du trait
			pen = QPen(Qt.GlobalColor.white)
			pen.setStyle(Qt.PenStyle.DotLine)
			painter.setPen(pen)
			
			# Dessiner un trait en pointillé blanc sur toute la hauteur du canvas
			painter.drawLine(self.spectrogram_width - 1, 0, self.spectrogram_width - 1, self.spectrogram_height)

			# Ajouter l'heure et les minutes au marqueur
			current_time = datetime.now().strftime("%Hh%M")
			
			# Sauvegarder la transformation actuelle pour la restaurer plus tard
			painter.save()
			
			# Définir la transformation : translation et rotation
			painter.translate(self.spectrogram_width - 10, self.spectrogram_height)
			painter.rotate(-90)  # Faire pivoter de 90 degrés vers la gauche

			# Dessiner le texte (à la verticale, aligné sur le bas)
			painter.drawText(0, 5, current_time)  # Aligner le texte sur le bas

			# Restaurer la transformation originale
			painter.restore()

			# Désactiver le marqueur après le dessin
			self.should_draw_marker = False


		# Terminer le dessin
		painter.end()

		# Mettre à jour l'affichage
		self.update()

	def draw_time_marker(self):
		# Indiquer qu'il faut dessiner le trait marqueur
		self.should_draw_marker = True
		self.update()

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.drawImage(0, 0, self.image)

	def resizeEvent(self, event):
		# Récupérer la nouvelle largeur et hauteur de la fenêtre
		new_width = self.width()
		new_height = self.height()

		# Créer une nouvelle image avec les nouvelles dimensions, remplie de noir
		new_image = QImage(new_width, new_height, QImage.Format.Format_RGB32)
		new_image.fill(Qt.GlobalColor.black)

		# Calculer les dimensions minimales à copier
		copy_width = min(new_width, self.spectrogram_width)
		copy_height = min(new_height, self.spectrogram_height)

		# Dessiner l'ancienne image dans la nouvelle image
		painter = QPainter(new_image)
		# Calculer l'offset (on va copier autant d'image que possible dans la nouvelle taille)
		offset_x = max(0, new_width - self.spectrogram_width)

		# Déterminer quelle partie de l'image copier, soit tout ou partie de l'ancienne image
		painter.drawImage(offset_x, 0, self.image, self.spectrogram_width - copy_width, 0, copy_width, copy_height)

		# Terminer le dessin
		painter.end()

		# Remplacer l'image par la nouvelle version redimensionnée
		self.image = new_image

		# Mettre à jour les dimensions
		self.spectrogram_width = new_width
		self.spectrogram_height = new_height

		# Forcer la mise à jour pour refléter le changement de taille
		self.update()

		# Appeler la méthode de la classe parente
		super().resizeEvent(event)

		
class StationDetailsDialog(QDialog):
	def __init__(self, parent):
		super().__init__(parent)
		self.setWindowTitle("Station Details")
		self.parent = parent
		self.config = parent.config
		
		form_layout = QFormLayout()

		# Callsign
		self.callsign_input = QLineEdit()
		self.callsign_input.textChanged.connect(lambda: self.parent.to_uppercase(self,self.callsign_input))	
		self.callsign_input.setText(self.parent.callsign)
		form_layout.addRow("Callsign:", self.callsign_input)

		# Grid with Autogrid checkbox
		self.grid_input = QLineEdit()
		self.grid_input.textChanged.connect(lambda: self.parent.to_uppercase(self,self.grid_input))	
		self.grid_input.setText(self.parent.grid)
		self.autogrid_checkbox = QCheckBox("Autogrid")
		self.autogrid_checkbox.setChecked(self.parent.autogrid)
		grid_layout = QHBoxLayout()
		grid_layout.addWidget(self.grid_input)
		grid_layout.addWidget(self.autogrid_checkbox)
		form_layout.addRow("Grid:", grid_layout)

		# Power
		self.power_input = QLineEdit()
		self.power_input.setText(self.parent.power)
		form_layout.addRow("Power (dBm):", self.power_input)

		# Dialog buttons (OK/Cancel)
		button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
		button_box.accepted.connect(self.accept)
		button_box.rejected.connect(self.reject)

		main_layout = QVBoxLayout()
		main_layout.addLayout(form_layout)
		main_layout.addWidget(button_box)

		self.setLayout(main_layout)

	def accept(self):
		# Validate Callsign
		callsign_pattern = re.compile(r"^[A-Z]{1,3}[0-9][A-Z0-9]{1,3}$")
		callsign = self.callsign_input.text().strip().upper()  # Convert to uppercase for uniformity
		if not callsign_pattern.match(callsign):
			self.parent.show_error_message("Invalid callsign. It should follow the format of an international amateur radio callsign.")
			return

		# Validate Grid
		grid = self.grid_input.text().strip().upper()  # Convert to uppercase for uniformity
		grid_pattern = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2})?$")
		if not grid_pattern.match(grid):
			self.parent.show_error_message("Invalid grid locator. It must be 4 or 6 characters long (e.g., 'AA00' or 'AA00AA').")
			return

		# Validate Power
		try:
			power = int(self.power_input.text().strip())
			if power < 0 or power > 60:
				self.parent.show_error_message("Power must be between 0 and 60 dBm.")
				return
		except ValueError:
			self.parent.show_error_message("Power must be an integer.")
			return

		# Update the parent's attributes
		self.parent.callsign = callsign
		self.parent.grid = grid
		self.parent.autogrid = self.autogrid_checkbox.isChecked()
		self.parent.power = str(power)

		# Save to configuration file
		self.parent.config["Station"] = {
			"callsign": self.parent.callsign,
			"grid": self.parent.grid,
			"autogrid": str(self.parent.autogrid),
			"power": self.parent.power
		}
		with open("config.ini", "w") as configfile:
			self.parent.config.write(configfile)

		super().accept()

class FrequencyShiftDialog(QDialog):
	def __init__(self, parent):
		super().__init__(parent)
		self.setWindowTitle("Frequency Shift Settings")
		self.parent = parent
		
		# Radio buttons for shift mode
		self.random_shift = QRadioButton("Random shift")
		self.fixed_shift = QRadioButton("Fixed shift")
		
		# Set the initial state based on parent's shift mode
		if parent.shift_mode == "random":
			self.random_shift.setChecked(True)
		else:
			self.fixed_shift.setChecked(True)
		
		# Input field for fixed shift value
		shift_value = parent.frequency_shift_value
		self.frequency_shift_value_input = QLineEdit(str(shift_value))
		self.frequency_shift_value_input.setPlaceholderText("Enter between 1400-1600 Hz")
		
		shift_mode_group = QButtonGroup()
		shift_mode_group.addButton(self.random_shift)
		shift_mode_group.addButton(self.fixed_shift)
		
		layout = QVBoxLayout()
		layout.addWidget(self.random_shift)
		layout.addWidget(self.fixed_shift)
		layout.addWidget(QLabel("Shift Frequency (Hz):"))
		layout.addWidget(self.frequency_shift_value_input)
		
		button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
		button_box.accepted.connect(self.accept)
		button_box.rejected.connect(self.reject)
		layout.addWidget(button_box)
		
		self.setLayout(layout)

	def accept(self):
		if self.fixed_shift.isChecked():
			try:
				shift_value = int(self.frequency_shift_value_input.text().strip())
				if shift_value < 1400 or shift_value > 1600:
					self.parent.show_error_message("Shift frequency must be between 1400 and 1600 Hz.")
					return
			except ValueError:
				self.parent.show_error_message("Shift frequency must be an integer.")
				return
		
		super().accept()

class AudioConfDialog(QDialog):
	def __init__(self, parent):
		super().__init__(parent)
		self.setWindowTitle("Audio Configuration")
		self.parent = parent

		# Layout principal
		layout = QVBoxLayout()

		# Liste déroulante pour les périphériques audio
		self.audio_device_combo = QComboBox()
		layout.addWidget(QLabel("Select Audio Input Device:"))
		layout.addWidget(self.audio_device_combo)

		# Récupérer la liste des périphériques audio disponibles
		self.devices = QMediaDevices.audioInputs()
		for device in self.devices:
			self.audio_device_combo.addItem(device.description(), device)

		# Pré-sélectionner l'appareil actuel
		current_device_id = self.parent.audio_device.id()
		for i, device in enumerate(self.devices):
			if str(device.id()) == str(current_device_id):
				self.audio_device_combo.setCurrentIndex(i)
				break

		# Dialog buttons (OK/Cancel)
		button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
		button_box.accepted.connect(self.accept)
		button_box.rejected.connect(self.reject)
		layout.addWidget(button_box)
		self.setLayout(layout)

	def accept(self):
		# Récupérer le périphérique sélectionné
		selected_device = self.audio_device_combo.currentData()
		if selected_device:
			# Mettre à jour le périphérique audio dans l'objet parent
			self.parent.audio_device = selected_device
			
			# Sauvegarder l'identifiant du périphérique audio dans la configuration
			self.parent.config["Audio"] = {
				"device_id": selected_device.id()
			}
			
			# Redémarrer l'audio avec le nouveau périphérique
			self.parent.setup_audio()

		super().accept()

	def get_selected_device(self):
		# Retourner l'identifiant du périphérique sélectionné
		index = self.audio_device_combo.currentIndex()
		if index != -1:
			return self.devices[index]
		return None

class AudioProcessor:
	def __init__(self, config, canvas):
		# Chargement de la configuration et du canvas pour l'affichage
		self.config = config
		self.canvas = canvas
		# Initialisation du buffer et taille de la FFT
		self.fft_size = 65536
		self.buffer = np.zeros(self.fft_size, dtype=np.int16)
		
		# buffer intermediaire pour la taille de l'overlap
		self.audio_buffer_accumulator = np.array([], dtype=np.int16)
		self.audio_buffer_accumulator_sub_size = 16384 # 0,341333 entre chaque fft
		
	   # Création de la fenêtre sinusoïdale pour le fenêtrage de `self.buffer`
		#self.window = np.sin(np.pi * np.arange(self.fft_size) / self.fft_size)  # sin(pi * i / 65536)
		self.window = 0.5 * (1 - np.cos(2 * np.pi * np.arange(self.fft_size) / (self.fft_size - 1)))

		self.reset_buffers()

	def reset_buffers(self):
		#Création du tableau des données final pour le traitement du décodage soit 512 fréquences de fft sur 375hz et 352 fenetres de 1,3653s d'echantillons sépraré de 0.341s d'interval 
		self.WSData_buffer = np.zeros((512, 359))  # Tampon circulaire pour les données filtrées WS 512 fréquences pour 359 fft pour les futurs calculs sauf que en réalité nous en aurons que 333 sur 114s
		self.current_fft_index = 0 
		self.WSData_buffer_avg = np.zeros(512)
		self.flag_get_audio_data = 0
		

	def setup_audio(self):
		# Arrêter l'audio actuel si nécessaire
		if hasattr(self, 'audio_source') and self.audio_source:
			self.audio_source.stop()
			
		# Définir le format de l'audio
		audio_format = QAudioFormat()
		audio_format.setChannelCount(1)
		audio_format.setSampleRate(48000)
		audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

		# Charger l'identifiant du périphérique audio depuis le fichier de configuration s'il n'a pas été déjà défini
		device_id = self.config.get("Audio", "device_id", fallback=None)
			
		# Rechercher le périphérique correspondant ou utiliser celui par défaut
		devices = QMediaDevices.audioInputs()
		device = None
		for d in devices:
			print(f"{device_id}")
			print(f"{d.id()} {d.description()}")
			if str(d.id()) == str(device_id):
				device = d
				print("Selected device based on configuration:", d.description())
				break
		
		# Si aucun périphérique correspondant n'est trouvé, utiliser le périphérique par défaut
		if device is None:
			device = QMediaDevices.defaultAudioInput()
			print("No matching device found. Using default audio input:", device.description())

		# Stocker le périphérique sélectionné dans self.audio_device
		self.audio_device = device

		# Créer QAudioSource avec le périphérique et le format défini
		self.audio_source = QAudioSource(device, audio_format)
		self.audio_buffer = self.audio_source.start()
		self.audio_buffer.readyRead.connect(self.accumulate_samples)
		
	def accumulate_samples(self):
		# Lire toutes les données disponibles dans le tampon audio
		data = self.audio_buffer.readAll()
		samples = np.frombuffer(data, dtype=np.int16)
		
		# Ajouter les échantillons au tampon accumulateur
		self.audio_buffer_accumulator = np.append(self.audio_buffer_accumulator, samples)
		
		# Traiter par blocs de 16384 échantillons
		while len(self.audio_buffer_accumulator) >= self.audio_buffer_accumulator_sub_size:
			# Récupérer exactement 16384 échantillons
			chunk = self.audio_buffer_accumulator[:self.audio_buffer_accumulator_sub_size]
			self.audio_buffer_accumulator = self.audio_buffer_accumulator[self.audio_buffer_accumulator_sub_size:]
			
			# Appeler process_audio_data avec le bloc de 16384 échantillons
			self.process_audio_data(chunk)

	def process_audio_data(self, samples):
		
		self.buffer = np.roll(self.buffer, -self.audio_buffer_accumulator_sub_size)
		self.buffer[-self.audio_buffer_accumulator_sub_size:] = samples
		
		#A remplacer par FFT inverse!!!!
		self.analytic_signal = hilbert(samples / 32768.0)
		
		windowed_buffer = self.buffer * self.window
		
		# Effectuer la FFT avec une taille fixée à `fft_size`
		fft_result = np.fft.fft(windowed_buffer, n=self.fft_size)
		freqs = np.fft.fftfreq(self.fft_size, d=1/48000)

		# Filtrer les fréquences entre 1300 et 1700 Hz
		mask = (freqs >= 1300) & (freqs <= 1700)
		# S'assurer que le masque a la même taille que fft_result
		filtered_fft = np.abs(fft_result[mask])
		# Mettre à jour le graphique avec les nouvelles données FFT
		self.canvas.update_data(filtered_fft)
					
		if self.flag_get_audio_data == 1:
			# Filtrer les fréquences entre 1312.5 et 1687.5 Hz pour le buffer circulaire
			#band_center = 1500, bandwidth = 375 => start_frequency = 1312.5 & end_frequency = 1687.5
			specific_mask = (freqs >= 1313) & (freqs <= 1688)
			#specific_filtered_fft = np.abs(fft_result[specific_mask])
			fft_result_masqued = fft_result[specific_mask]
			specific_filtered_fft = np.real(fft_result_masqued) ** 2 + np.imag(fft_result_masqued) ** 2

			# Ajouter les nouvelles données au buffer circulaire
			self.WSData_buffer[:, self.current_fft_index] = specific_filtered_fft
			self.WSData_buffer_avg += specific_filtered_fft
			
			self.current_fft_index = self.current_fft_index + 1
		
		if self.current_fft_index == 334: #(114s)
			# Instancier la classe `WSDecode_messages` et démarrer le thread pour afficher les spectres
			self.ws_decode_thread = WSDecode_messages(self.WSData_buffer,self.WSData_buffer_avg)
			self.ws_decode_thread.start()
			self.reset_buffers()
			
		
class Candidate:
	def __init__(self):
		self.freq = 0.0
		self.snr = 0.0
		self.drift = 0.0
		self.shift = 0
		self.sync = 0.0

class WSDecode_messages(QThread):
	def __init__(self, buffer, buffer_avg):
		super().__init__()
		self.buffer = buffer
		self.buffer_avg = buffer_avg
			
	def run(self):
		
		#Smooth with 7-point window and limit spectrum to +/-150 Hz
		# Création de la fenêtre (inutile d'utiliser une boucle pour une fenêtre uniforme)
		window = np.ones(7)
		# Calcul de l'indice de départ pour buffer_avg
		indices = np.arange(411).reshape(-1, 1) + np.arange(-3, 4)  # Crée une matrice des indices pour chaque 'i' et 'j'
		indices += (256 - 205)  # Applique le décalage sur chaque indice
		# Récupération des valeurs depuis buffer_avg en utilisant les indices
		buffer_avg_values = self.buffer_avg[indices]
		# Application de la fenêtre sur les valeurs récupérées et somme le long de l'axe des 'j'
		smspec = np.sum(buffer_avg_values * window, axis=1)
		
		tmpsort = np.sort(smspec)
		noise_level = tmpsort[122]

		# Données d'entrée
		df = 375.0/256.0/2  # Fréquence de résolution
		snr_scaling_factor = 26.3
		min_snr = 10 ** (-8.0 / 10.0)  # SNR minimal en dB pour la bande WSPR
		
		smspec = smspec / noise_level - 1.0
		smspec = np.where(smspec < min_snr, 0.1 * min_snr, smspec)

		# Calculer fmin et fmax, en tenant compte de l'erreur de fréquence du cadran
		fmin = -150  # Erreur de fréquence minimale en Hz
		fmax = 150   # Erreur de fréquence maximale en Hz
		
		# Initialisation d'une liste dynamique pour stocker les candidats
		candidates = []
				
		# Calculer les maxima locaux dans smspec
		local_maxima_indices = argrelextrema(smspec, np.greater)[0]

		# Créer une liste des candidats à partir des maxima locaux
		filtered_candidates_indices = [j for j in local_maxima_indices if 1 <= j < 410]

		# Limiter la liste de candidats à un maximum de 200 et les filtrer par fmin et fmax
		for j in filtered_candidates_indices:
			candidate_freq = (j - 205) * df
			if len(candidates) < 200 and fmin <= candidate_freq <= fmax:
				# Créer un nouveau candidat
				candidate = Candidate()
				candidate.freq = candidate_freq
				candidate.snr = 10 * np.log10(smspec[j]) - snr_scaling_factor
				candidates.append(candidate)

		# sort sur snr pour trier les candidats par ordre décroissant de snr
		candidates.sort(key=lambda x: x.snr, reverse=True)
		
		maxdrift=2
		nffts = len(self.buffer)

		print(len(candidates))
		
		print("\n\n")
		# Vérification des valeurs des premiers candidats pour débogage
		for i in range(min(10, len(candidates))):
			candidates[i].freq = 1500 + candidates[i].freq
			print(vars(candidates[i]))
		print("\n\n")
			

class WSQSOInterface(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("WSPRQSO by F4HTB")
		self.setGeometry(100, 100, 800, 600)
		self.setWindowIcon(QIcon("icon.png"))
		
		# Initialize config parser
		self.config = configparser.ConfigParser()
		self.config.read("config.ini")

		# Initialize station details
		self.callsign = self.config.get("Station", "callsign", fallback="")
		self.grid = self.config.get("Station", "grid", fallback="")
		self.autogrid = self.config.getboolean("Station", "autogrid", fallback=False)
		self.power = self.config.get("Station", "power", fallback="")
		
		# Initialize default shift mode and value
		self.shift_mode = self.config.get("Settings", "shift_mode", fallback="random")
		if self.shift_mode == "random":
			self.frequency_shift_value = random.randint(1400, 1600)
		else:
			self.frequency_shift_value = int(self.config.get("Settings", "frequency_shift_value", fallback="1500"))
	
		# Band frequencies (MHz)
		self.band_frequencies = {
			"2200m": 138500,
			"630m": 475200,
			"160m": 1839600,
			"80m": 3569600,
			"60m": 5288200,
			"40m": 7041100,
			"30m": 10141200,
			"20m": 14098100,
			"17m": 18107100,
			"15m": 21097100,
			"12m": 24927100,
			"10m": 28127100,
			"6m": 50295500,
			"4m": 70092000,
			"2m": 144490000
		}

		# Load selected band from config or set default
		self.selected_band = self.config.get("Settings", "selected_band", fallback="40m")

		main_widget = QWidget()
		self.setCentralWidget(main_widget)
		
		# Menu Bar
		menu_bar = self.menuBar()
		
		# File Menu
		file_menu = menu_bar.addMenu("File")
		exit_action = QAction("Exit", self)
		exit_action.triggered.connect(self.close)
		file_menu.addAction(exit_action)
		
		# Configuration Menu
		config_menu = menu_bar.addMenu("Configuration")
		
		# Station Details Action in Configuration Menu
		station_details_action = QAction("Station details", self)
		station_details_action.triggered.connect(self.open_station_details)
		config_menu.addAction(station_details_action)
		
		# Frequencies Action to open FrequencyShiftDialog
		frequencies_action = QAction("Frequencies", self)
		frequencies_action.triggered.connect(self.open_frequency_shift_dialog)
		config_menu.addAction(frequencies_action)
		
		# Frequencies Action to open FrequencyShiftDialog
		audioconf_action = QAction("Audio", self)
		audioconf_action.triggered.connect(self.open_audioconf_dialog)
		config_menu.addAction(audioconf_action)
		
		# Save Menu
		save_menu = menu_bar.addMenu("Save")
		save_menu.addAction("Save log settings")
		save_menu.addAction("Save log to")
		
		# Band Menu
		band_menu = menu_bar.addMenu("Band")
		self.band_action_group = QActionGroup(self)
		for band, freq in self.band_frequencies.items():
			action = QAction(band, self)
			action.setCheckable(True)
			action.triggered.connect(lambda checked, freq=freq, band=band: self.set_dial_frequency(freq, band))
			band_menu.addAction(action)
			self.band_action_group.addAction(action)

		# Initialize UI components before setting band
		main_layout = QGridLayout()
		
		#########
		# Waterfall canvas pour afficher les spectres
		self.canvas = WaterfallCanvas(self)
		self.canvas.setMinimumSize(400, 548)  # Définir une taille minimale pour garantir la visibilité
		#########

		#########
		# Ajouter l'échelle au layout principal pour le canvas
		self.scale_widget = FrequencyScaleWidget(self)
		self.scale_widget.setMinimumWidth(70)  # Ajuster la largeur minimale de l'échelle
		#########
		
		#########
		# Frequency section with QGroupBox
		freq_group = QGroupBox("Frequency (Hz)")
		freq_layout = QHBoxLayout()  # Utiliser un layout horizontal au lieu de QFormLayout
		# Frequency Dial and TX with fixed graphical width corresponding to 10 characters
		dial_label = QLabel("Dial:")
		self.dial_input = QLineEdit()
		self.dial_input.setMaxLength(10)
		self.dial_input.setFixedWidth(100)  # Width fixed to fit 10 characters approximately
		self.dial_input.returnPressed.connect(self.update_tx_frequency)  # Connecter à une fonction pour gérer le changement de dial_input
		# Input box pour le shift
		shift_freq_label = QLabel(" + Δ :")
		self.shift_freq_input = QLineEdit()
		self.shift_freq_input.setMaxLength(10)
		self.shift_freq_input.setFixedWidth(100)  # Taille adaptée
		self.shift_freq_input.returnPressed.connect(self.update_tx_frequency)  # Connecter à une fonction pour gérer le changement de shift_freq_input
		# TX Label and Input
		tx_label = QLabel(" = TX:")
		self.tx_input = QLineEdit()
		self.tx_input.setMaxLength(10)
		self.tx_input.setFixedWidth(100)  # Width fixed to fit 10 characters approximately
		self.tx_input.setReadOnly(True)
		# Ajouter les widgets au layout horizontal
		freq_layout.addWidget(dial_label)
		freq_layout.addWidget(self.dial_input)
		freq_layout.addWidget(shift_freq_label)
		freq_layout.addWidget(self.shift_freq_input)  # Ajouter la nouvelle input box de fréquence
		freq_layout.addWidget(tx_label)
		freq_layout.addWidget(self.tx_input)
		# Ajouter un espace extensible à la fin pour pousser les widgets vers la gauche
		freq_layout.addStretch()
		# Appliquer le layout horizontal au QGroupBox
		freq_group.setLayout(freq_layout)		
		#########
		
		#########
		# Messages Display Area
		self.message_display = QTextEdit()
		self.message_display.setReadOnly(True)
		#########
		
		#########
		# Transmit Button
		self.transmit_button = QPushButton("Transmit")
		self.transmit_button.clicked.connect(self.transmit_message)
		#########
		
		#########
		# Barre de progression pour le temps
		self.timer_progress = QProgressBar(self)
		self.timer_progress.setRange(0, 120)  # Plage de 0 à 200 secondes
		self.timer_progress.setValue(0)  # Valeur initiale
		self.timer_progress.setStyleSheet("QProgressBar{text-align: right;margin-right: 2em;} QProgressBar::chunk{background-color: #ff5733;text-align: center;}")
		self.timer_progress.setFormat("%v s")  # Afficher les secondes (0 à 200) suivies de "s"
		self.timer_progress.setStyleSheet("QProgressBar{text-align: right;margin-right: 2em;} QProgressBar::chunk{background-color: #00b050;text-align: center;}")

		# Layout pour aligner la barre de progression en bas à droite
		progress_layout = QHBoxLayout()
		progress_layout.addStretch()  # Ajoute de l'espace flexible à gauche pour pousser la barre vers la droite
		progress_layout.addWidget(self.timer_progress)
		#########
		
		#########
		# Créer un layout horizontal pour le canvas et l'échelle de fréquence
		canvas_scale_layout = QHBoxLayout()
		canvas_scale_layout.setSpacing(0)  # Enlever l'espace entre les widgets
		canvas_scale_layout.addWidget(self.canvas, stretch=1)  # Le canvas occupe tout l'espace restant
		canvas_scale_layout.addWidget(self.scale_widget)  # Ajouter l'échelle de fréquence juste à droite
		# Définir une taille maximale pour scale_widget pour qu'il n'occupe pas plus de place que nécessaire
		self.scale_widget.setMaximumWidth(100)  # Par exemple, une largeur de 100 pixels
		#########

		# Ajouter le layout horizontal au layout principal
		
		#########
		# Organizing layouts in main layout
		# Ajouter les autres éléments de l'interface
		main_layout.addLayout(canvas_scale_layout, 0, 0, 1, 3)  # Combiner les deux widgets sur toute la largeur (3 colonnes)
		main_layout.addWidget(freq_group, 1, 0, 1, 3)  # Frequency controls in QGroupBox
		main_layout.addWidget(self.transmit_button, 2, 0, 1, 3)  # Transmit button below inputs
		main_layout.addWidget(QLabel("QSO Log:"), 3, 0, 1, 3)
		main_layout.addWidget(self.message_display, 4, 0, 1, 3)  # Message display area
		main_layout.addLayout(progress_layout, 5, 0, 1, 3)  # Ajouter à la fin du layout principal
		main_widget.setLayout(main_layout)
		#########
		
		#########
		# Update shift frequency pinter
		self.scale_widget.set_shift_frequency(self.frequency_shift_value)
		#########
		
		#########
		# Set options after initializing components
		for action in self.band_action_group.actions():
			if action.text() == self.selected_band:
				action.setChecked(True)
				self.set_dial_frequency(self.band_frequencies[self.selected_band], self.selected_band)
		self.shift_freq_input.setText(str(self.frequency_shift_value))
		self.update_tx_frequency()
		#########
		
		#########
		# Create the TimerWorker and connect the signal
		self.timer_worker = TimerWorker()
		self.timer_worker.time_signal.connect(self.update_time_where)
		self.timer_worker.start()
		#########
		
		#########
		# Initialiser un buffer circulaire pour les fréquences entre 1400 et 1600 Hz (par exemple)
		#200 / (48000 / 32768) = 136.533 soit 137pix  * 60s * 2min = 16440
		self.WSPRcircular_buffer = collections.deque(maxlen=(16440))  # Taille définie pour 2 minutes de données, ajustez selon vos besoins
		#########
		
		# #########
		# # Configuration pour l'audio
		# # Instancier la classe AudioProcessor avec config et canvas
		self.audio_processor = AudioProcessor(self.config, self.canvas)
		# # Appeler setup_audio pour configurer et démarrer l'audio
		self.audio_processor.setup_audio()
		# #########
	
	def update_time_where(self, value):
		self.timer_progress.setValue(value)
		if value == 0:  # À chaque début de cycle de 200 secondes
			self.audio_processor.flag_get_audio_data = 1
			self.canvas.draw_time_marker()
			self.timer_progress.setStyleSheet("QProgressBar{text-align: right;margin-right: 2em;} QProgressBar::chunk{background-color: #00b050;text-align: center;}")
		if value == 114:
			self.timer_progress.setStyleSheet("QProgressBar{text-align: right;margin-right: 2em;} QProgressBar::chunk{background-color: #ff5733;text-align: center;}")

	@staticmethod
	def show_error_message(message):
		error_dialog = QMessageBox()
		error_dialog.setIcon(QMessageBox.Icon.Critical)
		error_dialog.setWindowTitle("Input Error")
		error_dialog.setText(message)
		error_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
		error_dialog.exec()
	
	@staticmethod
	def to_uppercase(self, line_edit):
		line_edit.blockSignals(True)  # Désactiver les signaux pour éviter la boucle infinie
		line_edit.setText(line_edit.text().upper())
		line_edit.blockSignals(False)  # Réactiver les signaux
	
	def set_dial_frequency(self, frequency, band):
		self.dial_input.setText(f"{int(frequency)}")
		self.selected_band = band
		# Update the checkmark in the Band menu
		for action in self.band_action_group.actions():
			action.setChecked(action.text() == band)
		self.update_tx_frequency()
	
	def update_tx_frequency(self):
		try:
			tx_freq = int(self.dial_input.text()) + int(self.shift_freq_input.text())
			self.tx_input.setText(f"{int(tx_freq)}")
		except ValueError:
			self.tx_input.setText("")

	def open_station_details(self):
		dialog = StationDetailsDialog(self)
		if dialog.exec() == QDialog.DialogCode.Accepted:
			self.message_display.append(f"Station Details - Callsign: {self.callsign}, Grid: {self.grid}, Power: {self.power} dBm, Autogrid: {self.autogrid}")
   
	def open_frequency_shift_dialog(self):
		dialog = FrequencyShiftDialog(self)
		if dialog.exec() == QDialog.DialogCode.Accepted:
			self.shift_mode = "random" if dialog.random_shift.isChecked() else "fixed"
			self.frequency_shift_value = int(dialog.frequency_shift_value_input.text() or "1500")
			self.shift_freq_input.setText(str(self.frequency_shift_value))

	def open_audioconf_dialog(self):
		dialog = AudioConfDialog(self)
		if dialog.exec() == QDialog.DialogCode.Accepted:
			selected_device = dialog.get_selected_device()
			if selected_device:
				# Utilisez le périphérique sélectionné, par exemple :
				self.audio_device = selected_device
				print(f"Selected audio device: {self.audio_device.description()}")

	
	def transmit_message(self):
		self.message_display.append("Simulated message transmission.")
	
	def closeEvent(self, event):
		# Only save fixed shift mode to config if it's selected
		self.config["Settings"] = {
			"shift_mode": self.shift_mode,
			"selected_band": self.selected_band,
		}
		if self.shift_mode == "fixed":
			self.config["Settings"]["frequency_shift_value"] = str(self.frequency_shift_value)
 
		# Save station details
		self.config["Station"] = {
			"callsign": self.callsign,
			"grid": self.grid,
			"autogrid": str(self.autogrid),
			"power": self.power
		}

		# Sauvegarder l'identifiant du périphérique audio
		if hasattr(self, 'audio_device') and self.audio_device:
			self.config["Audio"] = {
				"device_id": self.audio_device.id()
			}
 
		with open("config.ini", "w") as configfile:
			self.config.write(configfile)
		event.accept()

app = QApplication(sys.argv)
window = WSQSOInterface()
window.show()
sys.exit(app.exec())
