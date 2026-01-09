import tkinter as tk
import os
import sys

# Ensure display is set
os.environ["DISPLAY"] = ":0"

print("Starting Tkinter application...")
sys.stdout.flush()

try:
    root = tk.Tk()
    root.title("Tkinter Test")
    root.geometry("300x200")

    label = tk.Label(root, text="Hello from Tkinter", pady=20)
    label.pack()

    def on_click():
        print("Button clicked!")
        label.config(text="Tkinter is working!")

    button = tk.Button(root, text="Click Me", command=on_click)
    button.pack()

    print("Entering main loop...")
    sys.stdout.flush()
    root.mainloop()
except Exception as e:
    print(f"Error: {e}")
    sys.stdout.flush()
