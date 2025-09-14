import sys
import os
import json
import shlex
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QListWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QComboBox,
    QCheckBox, QTextEdit, QMenuBar, QAction, QSplitter, QFormLayout, QSpinBox
)
from PyQt5.QtCore import Qt, QProcess
from PyQt5.QtGui import QTextCursor, QIcon

HOME = os.path.expanduser("~")
VM_DIR = os.path.join(HOME, "Virtual Machines")
os.makedirs(VM_DIR, exist_ok=True)
import shutil
import tempfile

def vm_file_path(name):
    return os.path.join(VM_DIR, f"{name}.VM")

DEFAULT_VM_TEMPLATE = {
    "name": "unnamed",
    "memory": 2048,
    "cpus": 2,
    "display": "qxl",
    "vram": 16,
    "disk": "",
    "disk_format": "qcow2",
    "cdrom": "",
    "floppy": "",
    "audio": "AC97",
    "network": "user",
    "shared_folders": [],  # list of {"host_path": "/path", "tag": "hostshare"}
    "iso_drivers": "",     # path to driver ISO
    "enable_spice": False,
    "enable_guest_agent": False,
    "use_monitor_terminal": False
}

class VM:
    def __init__(self, data: dict):
        self.data = {**DEFAULT_VM_TEMPLATE, **data}
        self.data["name"] = self.data.get("name") or "unnamed"
    def save(self, folder=VM_DIR):
        path = vm_file_path(self.data["name"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)
    @staticmethod
    def load(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return VM(data)

    def build_qemu_cmd(self):
        args = ["qemu-system-x86_64"]

        name = self.data["name"]
        args += ["-name", name]

        args += ["-m", str(self.data["memory"])]
        args += ["-smp", str(self.data["cpus"])]

        args += ["-vga", "cirrus"]

        vram = str(self.data.get("vram", 16))
        args += ["-global", f"VGA.vgamem_mb={vram}"]

        audio = self.data.get("audio", "")
        if audio.upper() == "AC97":
            args += ["-device", "AC97"]

        net_device = self.data.get("network", "rtl8139")
        args += ["-netdev", "user,id=net0", "-device", f"{net_device},netdev=net0"]

        disk = self.data.get("disk")
        if disk:
            fmt = self.data.get("disk_format", "qcow2")
            args += ["-drive", f"file={disk},format={fmt},if=ide"]

        cdrom = self.data.get("cdrom")
        if cdrom:
            args += ["-cdrom", cdrom]
            args += ["-boot", "d"]

        floppy = self.data.get("floppy")
        if floppy and os.path.exists(floppy):
            args += ["-drive", f"file={floppy},format=raw,if=floppy,readonly=on"]


        iso_drivers = self.data.get("iso_drivers")
        if iso_drivers:
            args += ["-drive", f"file={iso_drivers},media=cdrom"]

        sf = self.data.get("shared_folders", [])
        for idx, share in enumerate(sf):
            host_path = share.get("host_path")
            tag = share.get("tag") or f"hostshare{idx}"
            if host_path:
                args += ["-virtfs", f"local,id=fs{idx},path={host_path},mount_tag={tag},security_model=mapped-file"]

        if self.data.get("enable_spice"):
            args += ["-spice", "port=5900,disable-ticketing,addr=127.0.0.1"]
            args += ["-device", "virtio-serial"]

        if self.data.get("enable_guest_agent"):
            pass

        if self.data.get("use_monitor_terminal"):
            args += ["-monitor", "stdio"]

        return args

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VirtManager")
        self.setWindowIcon(QIcon("icon.png"))
        self.resize(1000, 600)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        new_action = QAction("New VM", self)
        new_action.triggered.connect(self.new_vm_dialog)
        file_menu.addAction(new_action)
        import_action = QAction("Import VM (.VM)", self)
        import_action.triggered.connect(self.import_vm)
        file_menu.addAction(import_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)
        self.vm_list = QListWidget()
        self.vm_list.itemClicked.connect(self.on_vm_selected)
        left_layout.addWidget(QLabel("Virtual Machines"))
        left_layout.addWidget(self.vm_list)
        btn_layout = QHBoxLayout()
        btn_new = QPushButton("New")
        btn_new.clicked.connect(self.new_vm_dialog)
        btn_delete = QPushButton("Delete")
        btn_delete.clicked.connect(self.delete_vm)
        btn_clone = QPushButton("Save")
        btn_clone.clicked.connect(self.clone_vm)
        btn_layout.addWidget(btn_new); btn_layout.addWidget(btn_delete); btn_layout.addWidget(btn_clone)
        left_layout.addLayout(btn_layout)

        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("Name:", self.name_edit)
        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(128, 65536)
        self.memory_spin.setValue(2048)
        form.addRow("Memory (MB):", self.memory_spin)
        self.cpus_spin = QSpinBox()
        self.cpus_spin.setRange(1, 64)
        self.cpus_spin.setValue(2)
        form.addRow("CPUs:", self.cpus_spin)
        self.display_combo = QComboBox()
        self.display_combo.addItems(["std", "qxl", "virtio", "cirrus"])
        form.addRow("VGA Device:", self.display_combo)
        self.audio_combo = QComboBox()
        self.audio_combo.addItems(["AC97", "es1370", "sb16"])
        form.addRow("Audio Device:", self.audio_combo)
        self.network_combo = QComboBox()
        self.network_combo.addItems(["rtl8139", "e1000", "virtio-net", "ne2k_pci"])
        form.addRow("Network Device:", self.network_combo)
        self.vram_spin = QSpinBox()
        self.vram_spin.setRange(2, 512)
        self.vram_spin.setValue(16)
        form.addRow("VRAM (MB):", self.vram_spin)

        disk_hlayout = QHBoxLayout()
        self.disk_path = QLineEdit()
        disk_btn = QPushButton("Select Disk")
        disk_btn.clicked.connect(lambda: self.select_file(self.disk_path))
        disk_create_btn = QPushButton("Create Disk")
        disk_create_btn.clicked.connect(self.create_disk)
        disk_hlayout.addWidget(self.disk_path); disk_hlayout.addWidget(disk_btn); disk_hlayout.addWidget(disk_create_btn)
        form.addRow("Disk file:", disk_hlayout)

        self.disk_format = QComboBox()
        self.disk_format.addItems(["qcow2", "vdi", "vmdk", "raw"])
        form.addRow("Disk format:", self.disk_format)

        cd_hlayout = QHBoxLayout()
        self.cd_path = QLineEdit()
        cd_btn = QPushButton("Select CD-ROM / ISO")
        cd_btn.clicked.connect(lambda: self.select_file(self.cd_path))
        cd_hlayout.addWidget(self.cd_path); cd_hlayout.addWidget(cd_btn)
        form.addRow("CD-ROM / ISO:", cd_hlayout)

        iso_hlayout = QHBoxLayout()
        self.iso_drivers = QLineEdit()
        iso_btn = QPushButton("Select Drivers ISO")
        iso_btn.clicked.connect(lambda: self.select_file(self.iso_drivers))
        iso_hlayout.addWidget(self.iso_drivers); iso_hlayout.addWidget(iso_btn)
        form.addRow("Drivers ISO:", iso_hlayout)

        floppy_hlayout = QHBoxLayout()
        self.floppy_path = QLineEdit()
        floppy_btn = QPushButton("Select Floppy")
        floppy_btn.clicked.connect(lambda: self.select_file(self.floppy_path))
        floppy_hlayout.addWidget(self.floppy_path)
        floppy_hlayout.addWidget(floppy_btn)
        form.addRow("Floppy Disk:", floppy_hlayout)

        self.shared_folders_text = QTextEdit()
        self.shared_folders_text.setPlaceholderText('Each line: /host/path::mount_tag (example: /home/user/share::hostshare)')
        form.addRow("Shared Folders (9p):", self.shared_folders_text)

        self.spice_chk = QCheckBox("Enable SPICE (suggested for clipboard/resize)")
        form.addRow(self.spice_chk)
        self.gagent_chk = QCheckBox("Enable qemu-guest-agent (guest must have it installed)")
        form.addRow(self.gagent_chk)
        self.monitor_chk = QCheckBox("Run monitor in terminal (connects stdin/stdout)")
        form.addRow(self.monitor_chk)

        btn_save = QPushButton("Save VM (.VM)")
        btn_save.clicked.connect(self.save_vm)
        btn_start = QPushButton("Start VM")
        btn_start.clicked.connect(self.start_vm)
        btn_layout2 = QHBoxLayout()
        btn_layout2.addWidget(btn_save); btn_layout2.addWidget(btn_start)
        form.addRow(btn_layout2)

        right_layout.addLayout(form)

        right_layout.addWidget(QLabel("VM Console / Monitor"))
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(False)
        right_layout.addWidget(self.terminal)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)

        self.proc = None
        self.load_vms()

    def create_disk(self):
        from PyQt5.QtWidgets import QInputDialog
        file_path, _ = QFileDialog.getSaveFileName(self, "Create Virtual Disk", HOME, "Disk files (*.img *.qcow2 *.vdi *.vmdk)")
        if not file_path:
            return

        fmt_items = ["qcow2", "raw", "vdi", "vmdk"]
        fmt, ok = QInputDialog.getItem(self, "Select Disk Format", "Format:", fmt_items, 0, False)
        if not ok:
            return

        size, ok = QInputDialog.getText(self, "Disk Size", "Enter size (e.g., 10G, 500M):")
        if not ok or not size.strip():
            return

        cmd = ["qemu-img", "create", "-f", fmt, file_path, size.strip()]
        self.terminal.append("> " + " ".join(cmd))
        try:
            subprocess.check_call(cmd)
            QMessageBox.information(self, "Disk Created", f"Virtual disk created:\n{file_path}")
            self.disk_path.setText(file_path)
            self.disk_format.setCurrentText(fmt)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create disk: {e}")


    def select_file(self, lineedit: QLineEdit):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select file")
        if file_path:
            lineedit.setText(file_path)

    def load_vms(self):
        self.vm_list.clear()
        for fname in os.listdir(VM_DIR):
            if fname.endswith(".VM"):
                self.vm_list.addItem(os.path.splitext(fname)[0])

    def on_vm_selected(self, item):
        name = item.text()
        path = vm_file_path(name)
        try:
            vm = VM.load(path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load VM file: {e}")
            return
        d = vm.data
        self.name_edit.setText(d.get("name", ""))
        self.memory_spin.setValue(d.get("memory", 2048))
        self.cpus_spin.setValue(d.get("cpus", 2))
        self.display_combo.setCurrentText(d.get("display", "qxl"))
        self.audio_combo.setCurrentText(d.get("audio", "AC97"))
        self.network_combo.setCurrentText(d.get("network", "rtl8139"))
        self.vram_spin.setValue(d.get("vram", 16))
        self.disk_path.setText(d.get("disk", ""))
        self.disk_format.setCurrentText(d.get("disk_format", "qcow2"))
        self.cd_path.setText(d.get("cdrom", ""))
        self.iso_drivers.setText(d.get("iso_drivers", ""))
        self.floppy_path.setText(d.get("floppy", ""))
        lines = []
        for s in d.get("shared_folders", []):
            hp = s.get("host_path", "")
            tag = s.get("tag", "")
            lines.append(f"{hp}::{tag}")
        self.shared_folders_text.setPlainText("\n".join(lines))
        self.spice_chk.setChecked(bool(d.get("enable_spice", False)))
        self.gagent_chk.setChecked(bool(d.get("enable_guest_agent", False)))
        self.monitor_chk.setChecked(bool(d.get("use_monitor_terminal", False)))

    def save_vm(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter VM name.")
            return
        data = {
            "name": name,
            "memory": int(self.memory_spin.value()),
            "cpus": int(self.cpus_spin.value()),
            "display": self.display_combo.currentText(),
            "audio": self.audio_combo.currentText(),
            "network": self.network_combo.currentText(),
            "vram": int(self.vram_spin.value()),
            "disk": self.disk_path.text().strip(),
            "disk_format": self.disk_format.currentText(),
            "cdrom": self.cd_path.text().strip(),
            "iso_drivers": self.iso_drivers.text().strip(),
            "floppy": self.floppy_path.text().strip(),
            "shared_folders": [],
            "enable_spice": self.spice_chk.isChecked(),
            "enable_guest_agent": self.gagent_chk.isChecked(),
            "use_monitor_terminal": self.monitor_chk.isChecked()
        }
        raw = self.shared_folders_text.toPlainText().strip()
        if raw:
            for line in raw.splitlines():
                if "::" in line:
                    hp, tag = line.split("::", 1)
                    data["shared_folders"].append({"host_path": hp.strip(), "tag": tag.strip()})
        vm = VM(data)
        try:
            vm.save()
            self.load_vms()
            QMessageBox.information(self, "Saved", f"VM '{name}' saved to {vm_file_path(name)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save VM: {e}")

    def start_vm(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter VM name to start.")
            return
        path = vm_file_path(name)
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "VM file not found. Save VM first.")
            return
        vm = VM.load(path)
        cmd = vm.build_qemu_cmd()
        self.terminal.append("> " + " ".join(shlex.quote(x) for x in cmd))
        try:
            if vm.data.get("use_monitor_terminal"):
                self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, universal_newlines=True)
                from threading import Thread
                def reader():
                    try:
                        for line in self.proc.stdout:
                            self.terminal.append(line.rstrip("\n"))
                    except Exception as e:
                        self.terminal.append(f"[reader error] {e}")
                t = Thread(target=reader, daemon=True)
                t.start()
            else:
                self.proc = subprocess.Popen(cmd)
                self.terminal.append(f"VM started (pid={self.proc.pid}).")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start VM: {e}")

    def delete_vm(self):
        item = self.vm_list.currentItem()
        if not item:
            QMessageBox.information(self, "Info", "Select a VM to delete.")
            return
        name = item.text()
        path = vm_file_path(name)
        confirm = QMessageBox.question(self, "Confirm", f"Delete VM file and folder for '{name}'? (files only if exist)")
        if confirm != QMessageBox.Yes:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
            # try to remove directory with VM name in VM_DIR
            vm_folder = os.path.join(VM_DIR, name)
            if os.path.isdir(vm_folder):
                import shutil
                shutil.rmtree(vm_folder)
            self.load_vms()
            QMessageBox.information(self, "Deleted", f"VM '{name}' deleted.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to delete: {e}")

    def clone_vm(self):
        item = self.vm_list.currentItem()
        if not item:
            QMessageBox.information(self, "Info", "Select VM to clone.")
            return
        name = item.text()
        path = vm_file_path(name)
        vm = VM.load(path)
        new_name, ok = QFileDialog.getSaveFileName(self, "Save clone as (.VM)", VM_DIR, "VM files (*.VM)")
        if not ok or not new_name:
            return
        # ensure extension
        if not new_name.endswith(".VM"):
            new_name += ".VM"
        try:
            with open(new_name, "w", encoding="utf-8") as f:
                json.dump(vm.data, f, indent=4)
            self.load_vms()
            QMessageBox.information(self, "Cloned", f"Cloned to {new_name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to clone: {e}")

    def new_vm_dialog(self):
        # simple new VM using current form fields, with prompt for name
        name, ok = QFileDialog.getSaveFileName(self, "New VM file (.VM)", VM_DIR, "VM files (*.VM)")
        if not ok or not name:
            return
        if not name.endswith(".VM"):
            name += ".VM"
        # create default VM data based on form
        base = DEFAULT_VM_TEMPLATE.copy()
        base["name"] = os.path.splitext(os.path.basename(name))[0]
        vm = VM(base)
        try:
            vm.save()
            self.load_vms()
            QMessageBox.information(self, "Created", f"Created VM {name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create: {e}")

    def import_vm(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import VM (.VM)", "", "VM files (*.VM)")
        if not path:
            return
        try:
            vm = VM.load(path)
            # copy into VM_DIR
            dest = vm_file_path(vm.data["name"])
            if os.path.exists(dest):
                QMessageBox.warning(self, "Exists", f"A VM named '{vm.data['name']}' already exists.")
                return
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(vm.data, f, indent=4)
            self.load_vms()
            QMessageBox.information(self, "Imported", f"Imported {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to import: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
