import sys, random, re, configparser
import numpy as np
from PyQt6.QtWidgets import (
	QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
	QTextEdit, QVBoxLayout, QHBoxLayout, QFormLayout, QMenu, QGridLayout,
	QFrame, QCheckBox, QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QGroupBox, QMessageBox, QComboBox
)
from PyQt6.QtGui import QAction, QActionGroup, QPainter, QColor, QPen, QImage
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtMultimedia import QAudioInput, QAudioFormat, QMediaDevices, QAudioSource
import collections



class WaterfallCanvas(QWidget):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.spectrogram_height = 273
		self.spectrogram_width = 400
		self.image = QImage(self.spectrogram_width, self.spectrogram_height, QImage.Format.Format_RGB32)
		self.image.fill(Qt.GlobalColor.black)  # Remplir l'image avec du noir au démarrage
		self.update()  # Forcer la mise à jour pour afficher le fond noir

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

		# Terminer le dessin
		painter.end()

		# Mettre à jour l'affichage
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
		self.frequency_shift_value_input.setPlaceholderText("Enter between 500-2500 Hz")
		
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
				if shift_value < 500 or shift_value > 2500:
					self.parent.show_error_message("Shift frequency must be between 500 and 2500 Hz.")
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

class WSPRQSOInterface(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("WSPRQSO by F4HTB")
		self.setGeometry(100, 100, 800, 600)
		
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
			self.frequency_shift_value = random.randint(500, 2500)
		else:
			self.frequency_shift_value = int(self.config.get("Settings", "frequency_shift_value", fallback="1500"))
	
		# Band frequencies (MHz)
		self.band_frequencies = {
			"2200m": 0.1385,
			"630m": 0.4752,
			"160m": 1.8396,
			"80m": 3.5696,
			"60m": 5.2882,
			"40m": 7.0411,
			"30m": 10.1412,
			"20m": 14.0981,
			"17m": 18.1071,
			"15m": 21.0971,
			"12m": 24.9271,
			"10m": 28.1271,
			"6m": 50.2955,
			"4m": 70.0920,
			"2m": 144.4900
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
		

		# Waterfall canvas pour afficher les spectres
		self.canvas = WaterfallCanvas(self)
		self.canvas.setMinimumSize(400, 273)  # Définir une taille minimale pour garantir la visibilité
		main_layout.addWidget(self.canvas, 0, 0, 1, 2)
		
		# Frequency section with QGroupBox
		freq_group = QGroupBox("Frequency")
		freq_layout = QFormLayout()
		
		# Frequency Dial and TX with fixed graphical width corresponding to 10 characters
		dial_label = QLabel("Dial:")
		self.dial_input = QLineEdit()
		self.dial_input.setMaxLength(10)
		self.dial_input.setFixedWidth(100)  # Width fixed to fit 10 characters approximately
		self.dial_input.textChanged.connect(self.update_tx_frequency)
		
		tx_label = QLabel("TX:")
		self.tx_input = QLineEdit()
		self.tx_input.setMaxLength(10)
		self.tx_input.setFixedWidth(100)  # Width fixed to fit 10 characters approximately
		self.tx_input.setReadOnly(True)
		
		freq_layout.addRow(dial_label, self.dial_input)
		freq_layout.addRow(tx_label, self.tx_input)
		
		freq_group.setLayout(freq_layout)
		
		# Messages Display Area
		self.message_display = QTextEdit()
		self.message_display.setReadOnly(True)
		
		# Transmit Button
		self.transmit_button = QPushButton("Transmit")
		self.transmit_button.clicked.connect(self.transmit_message)
		
		# Organizing layouts in main layout
		main_layout.addWidget(self.canvas, 0, 0, 1, 2)	  # Canvas in top left
		main_layout.addWidget(freq_group, 1, 0)			 # Frequency controls in QGroupBox
		main_layout.addWidget(self.transmit_button, 2, 0, 1, 2)  # Transmit button below inputs
		main_layout.addWidget(QLabel("Message Log:"), 3, 0, 1, 2)
		main_layout.addWidget(self.message_display, 4, 0, 1, 2)  # Message display area

		main_widget.setLayout(main_layout)

		# Set the selected band after initializing components
		for action in self.band_action_group.actions():
			if action.text() == self.selected_band:
				action.setChecked(True)
				self.set_dial_frequency(self.band_frequencies[self.selected_band], self.selected_band)


		# Initialiser un buffer circulaire pour les fréquences entre 1400 et 1600 Hz (par exemple)
		#200 / (48000 / 32768) = 136.533 soit 137pix  * 60s * 2min = 16440
		self.WSPRcircular_buffer = collections.deque(maxlen=(16440))  # Taille définie pour 2 minutes de données, ajustez selon vos besoins
		# Configuration pour l'audio
		self.setup_audio()

	def setup_audio(self):
		# Arrêter l'audio actuel si nécessaire
		if hasattr(self, 'audio_source') and self.audio_source:
			self.audio_source.stop()
			
		# Définir le format de l'audio
		audio_format = QAudioFormat()
		audio_format.setSampleRate(48000)
		audio_format.setChannelCount(1)
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
		
		# Utiliser un QTimer pour lire les données de l'audio et effectuer la FFT
		self.timer = QTimer()
		self.timer.timeout.connect(self.process_audio_data)
		self.timer.start(50)  # Intervalle de 50 ms pour lire les données audio



	def process_audio_data(self):
		if self.audio_buffer.bytesAvailable() > 0:
			data = self.audio_buffer.readAll()
			samples = np.frombuffer(data, dtype=np.int16)
			if len(samples) > 0:
				# Définir la taille de la FFT comme la largeur du canvas
				fft_size = 32768
				
				# Si la taille des échantillons est inférieure à la taille de la FFT, remplissez-la avec des zéros
				if len(samples) < fft_size:
					samples = np.pad(samples, (0, fft_size - len(samples)), 'constant')

				# Effectuer la FFT avec une taille fixée à `fft_size`
				fft_result = np.fft.fft(samples, n=fft_size)
				freqs = np.fft.fftfreq(fft_size, d=1/48000)

				# Filtrer les fréquences entre 1300 et 1700 Hz
				mask = (freqs >= 1300) & (freqs <= 1700)
				# S'assurer que le masque a la même taille que fft_result
				filtered_fft = np.abs(fft_result[mask])
				# Mettre à jour le graphique avec les nouvelles données FFT
				self.canvas.update_data(filtered_fft)
				
				print(f"Length of new_data: {len(filtered_fft)}") 
				
				# Filtrer les fréquences entre 1400 et 1600 Hz pour le buffer circulaire
				specific_mask = (freqs >= 1400) & (freqs <= 1600)
				specific_filtered_fft = np.abs(fft_result[specific_mask])

				print(f"Length of new_data: {len(specific_filtered_fft)}")

				# Ajouter les nouvelles données au buffer circulaire
				self.WSPRcircular_buffer.extend(specific_filtered_fft)
	

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
		self.dial_input.setText(f"{frequency:.6f}")
		self.selected_band = band
		# Update the checkmark in the Band menu
		for action in self.band_action_group.actions():
			action.setChecked(action.text() == band)
		self.update_tx_frequency()
	
	def update_tx_frequency(self):
		try:
			dial_freq = float(self.dial_input.text())
			# Use previously generated random shift value if random mode is active
			shift_freq = self.frequency_shift_value
			tx_freq = dial_freq + (shift_freq / 1e6)  # Convert shift from Hz to MHz
			self.tx_input.setText(f"{tx_freq:.6f}")
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
			self.update_tx_frequency()

	def open_audioconf_dialog(self):
		dialog = AudioConfDialog(self)
		if dialog.exec() == QDialog.DialogCode.Accepted:
			selected_device = dialog.get_selected_device()
			if selected_device:
				# Utilisez le périphérique sélectionné, par exemple :
				self.audio_device = selected_device
				print(f"Selected audio device: {self.audio_device.description()}")
				self.update_tx_frequency()
	
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
window = WSPRQSOInterface()
window.show()
sys.exit(app.exec())
