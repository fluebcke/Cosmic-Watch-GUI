from PyQt6.QtWidgets import QStatusBar, QLabel


class StatusBar(QStatusBar):

    def __init__(self):

        super().__init__()

        self.connection_label = QLabel("Disconnected")
        self.response_label = QLabel("")

        self.addWidget(self.connection_label)

        # permanent widget stays right-aligned and doesn't get
        # pushed out by temporary messages
        self.addPermanentWidget(self.response_label)


    def set_connected(self, connected: bool, port: str = ""):

        if connected:
            self.connection_label.setText(f"Connected — {port}")
        else:
            self.connection_label.setText("Disconnected")
            self.response_label.setText("")


    def show_response(self, line: str):

        self.response_label.setText(line)
