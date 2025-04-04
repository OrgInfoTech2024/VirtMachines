from PyQt5.QtWidgets import *
from PyQt5.QtGui import QIcon
import sys
import os
import json

user_home = os.path.expanduser("~")
vm_dir = os.path.join(user_home, "Virtual Machines")
if not os.path.exists(vm_dir):
    os.makedirs(vm_dir)
vms_json_path = os.path.join(user_home, "Virtual Machines", "vms.json")
if not os.path.exists(vms_json_path):
    with open(vms_json_path, "w") as f:
        json.dump({}, f)

class CreateVMWindow(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent = parent
        self.setWindowTitle("Create Virtual Machine")
        self.setMinimumSize(400, 300)
        
        layout = QFormLayout()
        
        self.name_input = QLineEdit()
        layout.addRow("Name of Virtual Machine:", self.name_input)
        
        self.ram_input = QLineEdit("4")
        layout.addRow("RAM (MB):", self.ram_input)
        
        self.cpu_input = QLineEdit("1")
        layout.addRow("Processor(s):", self.cpu_input)
        
        self.display_combo = QComboBox()
        self.display_combo.addItems(["std", "qxl", "virtio", "cirrus"])
        layout.addRow("Type of Display:", self.display_combo)
        
        vram_sizes = [str(2**i) for i in range(4, 9)]
        self.vram_combo = QComboBox()
        self.vram_combo.addItems(vram_sizes)
        layout.addRow("VRAM (MB):", self.vram_combo)
        
        self.disk_button = QPushButton("Select Disk File")
        self.disk_button.clicked.connect(lambda: self.select_file(self.disk_button))
        self.create_disk_button = QPushButton("Create New Disk")
        self.create_disk_button.clicked.connect(self.create_disk)
        disk_layout = QHBoxLayout()
        disk_layout.addWidget(self.disk_button)
        disk_layout.addWidget(self.create_disk_button)
        layout.addRow("Disk:", disk_layout)
        
        self.cdrom_button = QPushButton("Select CD-ROM File")
        self.cdrom_button.clicked.connect(lambda: self.select_file(self.cdrom_button))
        layout.addRow("CD-ROM:", self.cdrom_button)
        
        self.floppy_button = QPushButton("Select Floppy File")
        self.floppy_button.clicked.connect(lambda: self.select_file(self.floppy_button))
        layout.addRow("FLOPPY:", self.floppy_button)
        
        self.audio_combo = QComboBox()
        self.audio_combo.addItems(["ac97", "hda", "es1370", "sb16"])
        layout.addRow("Audio Device:", self.audio_combo)
        
        self.network_combo = QComboBox()
        self.network_combo.addItems(["rtl8139", "e1000", "virtio-net", "ne2k_pci"])
        layout.addRow("Network:", self.network_combo)
        
        self.create_button = QPushButton("Create")
        self.create_button.clicked.connect(self.create_vm)
        layout.addRow(self.create_button)
        
        self.setLayout(layout)
    
    def select_file(self, button):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_name:
            button.setText(file_name)

    def create_disk(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a name for the virtual machine first.")
            return
        
        user = os.getenv("USER")
        
        vm_path = f"/home/{user}/Virtual Machines/{name}/"
        
        try:
            os.makedirs(vm_path, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create VM directory: {e}")
            return
        
        disk_size, ok = QInputDialog.getInt(self, "Disk Size", "Enter disk size (GB):", min=1, max=1000)
        if not ok:
            return

        disk_path = os.path.join(vm_path, f"{name}.img")
        
        command = f"qemu-img create -f qcow2 '{disk_path}' {disk_size}G"
        result = os.system(command)

        if result == 0 and os.path.exists(disk_path):
            self.disk_button.setText(disk_path)
            QMessageBox.information(self, "Success", f"Disk created: {disk_path} ({disk_size} GB)")
        else:
            QMessageBox.critical(self, "Error", "Failed to create disk image. Check qemu-img installation and permissions.")
        
    def create_vm(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a name for the virtual machine.")
            return
        
        vm_path = os.path.join(vm_dir, name)
        if not os.path.exists(vm_path):
            os.makedirs(vm_path)

        with open(vms_json_path, "r+") as f:
            vms = json.load(f)
            vms[name] = {"path": vm_path}
            f.seek(0)
            json.dump(vms, f, indent=4)        

        ram = self.ram_input.text()
        cpu = self.cpu_input.text()
        display = self.display_combo.currentText()
        vram = self.vram_combo.currentText()
        
        disk = self.disk_button.text() if self.disk_button.text() != "Select Disk File" else None
        cdrom = self.cdrom_button.text() if self.cdrom_button.text() != "Select CD-ROM File" else None
        floppy = self.floppy_button.text() if self.floppy_button.text() != "Select Floppy File" else None
        
        audio = self.audio_combo.currentText()
        network = self.network_combo.currentText()
        
        script_path = os.path.join(vm_path, f"{name}.sh")
        with open(script_path, "w") as script_file:
            script_file.write(f"""#!/bin/bash
    qemu-system-x86_64 \\
        -name {name} \\
        -m {ram} \\
        -smp {cpu} \\
        -vga {display} \\
        -global VGA.vgamem_mb={vram} \\
        -device {audio} \\
        -netdev user,id=net0 \\
        -device {network},netdev=net0 \\
        {'-drive file="' + disk + '"' if disk else ''} \\
        {'-cdrom "' + cdrom if cdrom else ''} \\
        {'-fda "' + floppy + '"' if floppy else ''}
    """)
        os.chmod(script_path, 0o755)
        self.parent.machines.addItem(name)
        QMessageBox.information(self, "Success", f"Virtual machine '{name}' created successfully.")
        self.accept()

class SettingsWindow(QDialog):
    def __init__(self, script_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 400)
        
        self.script_path = script_path

        layout = QVBoxLayout()

        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)

        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.save_changes)
        layout.addWidget(self.save_button)

        self.load_script()

        self.setLayout(layout)

    def load_script(self):
        try:
            with open(self.script_path, 'r') as file:
                content = file.read()
            self.text_edit.setText(content)
        except Exception as e:
            print(f"Error loading script: {e}")
            self.text_edit.setText("Error loading file.")

    def save_changes(self):
        try:
            with open(self.script_path, 'w') as file:
                content = self.text_edit.toPlainText()
                file.write(content)
            print("Changes saved successfully!")
        except Exception as e:
            print(f"Error saving changes: {e}")
        
        self.accept()

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("VirtMachines")
        self.setWindowIcon(QIcon("icon.png"))
        self.setMinimumSize(300, 300)

        toolbar = self.addToolBar("Virtual Machine")
        toolbar.addAction("Create", self.create_machine)
        toolbar.addAction("Delete", self.delete_machine)
        toolbar.addAction("Import", self.import_machine)
        toolbar.addAction("Settings", self.open_settings)
        toolbar.addAction("Run", self.run)

        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        layout = QHBoxLayout()
        centralWidget.setLayout(layout)

        self.machines = QListWidget()
        layout.addWidget(self.machines)

        self.load_virtual_machines()
    
    def load_virtual_machines(self):
        self.machines.clear()
        try:
            with open(vms_json_path, "r") as f:
                vms = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            vms = {}

        for vm_name in vms.keys():
            self.machines.addItem(vm_name)

    def create_machine(self):
        CreateVMWindow(self).exec_()

    def delete_machine(self):
        selected_item = self.machines.currentItem()
        if selected_item:
            name = selected_item.text()
            msg_box = QMessageBox()
            msg_box.setWindowTitle("Delete VM")
            msg_box.setText(f"Delete this Virtual Machine '{name}'?")
            remove_button = msg_box.addButton("Remove from list", QMessageBox.AcceptRole)
            delete_button = msg_box.addButton("Delete files", QMessageBox.DestructiveRole)
            cancel_button = msg_box.addButton("Cancel", QMessageBox.RejectRole)
            msg_box.exec_()
            
            if msg_box.clickedButton() == remove_button:
                with open(vms_json_path, "r+") as f:
                    vms = json.load(f)
                    if name in vms:
                        del vms[name]
                        f.seek(0)
                        f.truncate()
                        json.dump(vms, f, indent=4)
                self.machines.takeItem(self.machines.row(selected_item))
            
            elif msg_box.clickedButton() == delete_button:
                with open(vms_json_path, "r+") as f:
                    vms = json.load(f)
                    if name in vms:
                        vm_path = vms[name]["path"]
                        if os.path.exists(vm_path):
                            import shutil
                            shutil.rmtree(vm_path)
                        del vms[name]
                        f.seek(0)
                        f.truncate()
                        json.dump(vms, f, indent=4)
                self.machines.takeItem(self.machines.row(selected_item))
    
    def run(self):
        selected_item = self.machines.currentItem()
        if selected_item:
            name = selected_item.text()
            with open(vms_json_path, "r") as f:
                vms = json.load(f)
                if name in vms:
                    vm_path = vms[name]["path"]
                    script_path = os.path.join(vm_path, f"{name}.sh")
                    if os.path.exists(script_path):
                        os.system(f'sh "{script_path}"')
                    else:
                        QMessageBox.warning(self, "Error", "Startup script not found.")

    def import_machine(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select VM Script", "", "Shell Scripts (*.sh)")
        if not file_path:
            return

        vm_name = os.path.splitext(os.path.basename(file_path))[0]

        try:
            with open(vms_json_path, "r") as f:
                vms = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            vms = {}

        if vm_name in vms:
            QMessageBox.warning(self, "Warning", f"A VM named '{vm_name}' already exists!")
            return

        vms[vm_name] = {
            "path": os.path.dirname(file_path),
            "script": file_path
        }

        try:
            with open(vms_json_path, "w") as f:
                json.dump(vms, f, indent=4)
        except IOError as e:
            QMessageBox.critical(self, "Error", f"Failed to save vms.json: {str(e)}")
            return

        self.load_virtual_machines()

        QMessageBox.information(self, "Success", f"VM '{vm_name}' imported successfully!")

    def open_settings(self):
        selected_item = self.machines.currentItem()
        if selected_item:
            name = selected_item.text()

            try:
                with open(vms_json_path, "r") as f:
                    vms = json.load(f)
                    if name in vms:
                        vm_path = vms[name]["path"]
                        script_path = os.path.join(vm_path, f"{name}.sh")
                        if os.path.exists(script_path):
                            window = SettingsWindow(script_path)
                            window.exec_()
                        else:
                            QMessageBox.warning(self, "Error", f"Script file '{name}.sh' not found for VM '{name}'.")
                    else:
                        QMessageBox.warning(self, "Error", f"VM '{name}' not found in the list.")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                QMessageBox.warning(self, "Error", "Failed to load VM data.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec_())