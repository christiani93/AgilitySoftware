# show_raw_data.py
# Ein einfaches Skript, das sich nur mit dem Timy verbindet
# und alle empfangenen Rohdaten direkt in der Konsole anzeigt.

import sys
import time

try:
    import pythoncom
    import win32com.client
except ImportError:
    sys.exit("Fehler: Das Paket 'pywin32' muss installiert sein.")

# Diese Klasse fängt die Daten vom Timy ab
class TimyDataViewerEvents:
    def OnUSBInput(self, data):
        """Wird für jede Datenzeile vom Timy aufgerufen."""
        # Gib die empfangenen Daten ohne Veränderung aus
        print(data.strip())
    
    def OnConnectionOpen(self):
        print(">>> Verbindung zum Timy erfolgreich hergestellt. Lausche auf Daten...")

    def OnError(self, code, text):
        print(f"!!! FEHLER: Code {code} - {text}")

# Hauptprogramm
if __name__ == '__main__':
    print("--- Timy Raw Data Viewer ---")
    
    pythoncom.CoInitialize()
    timy_connection = None
    
    try:
        # Erstelle eine Verbindung zum Timy
        timy_connection = win32com.client.DispatchWithEvents('ALGEUSB.TimyUSB', TimyDataViewerEvents)
        timy_connection.Init()
        timy_connection.OpenConnection(0)
        
        # Endlosschleife, um auf Daten zu warten. Beenden mit CTRL+C.
        while True:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n>>> Programm wird beendet.")
    except Exception as e:
        print(f"\nEin kritischer Fehler ist aufgetreten: {e}")
    finally:
        # Stelle sicher, dass die Verbindung immer geschlossen wird
        if timy_connection:
            timy_connection.CloseConnection()
        pythoncom.CoUninitialize()
        print(">>> Verbindung geschlossen.")
