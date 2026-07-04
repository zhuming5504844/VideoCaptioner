from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QFileDialog
from qfluentwidgets import EditableComboBox, PushButton, SettingCard
from qfluentwidgets.common.config import ConfigItem, qconfig


class ApiKeyComboSettingCard(SettingCard):
    """API Key selector with paste/import/clear/delete actions."""

    keyChanged = pyqtSignal(str)

    def __init__(
        self,
        keyConfigItem: ConfigItem,
        keysConfigItem: ConfigItem,
        icon,
        title: str,
        content: str | None = None,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self.keyConfigItem = keyConfigItem
        self.keysConfigItem = keysConfigItem
        self._updating = False

        self.comboBox = EditableComboBox(self)
        self.comboBox.setMinimumWidth(310)

        self.pasteButton = PushButton(self.tr("粘贴"), self)
        self.importButton = PushButton(self.tr("导入"), self)
        self.clearButton = PushButton(self.tr("清空"), self)
        self.deleteButton = PushButton(self.tr("删除当前"), self)

        self.hBoxLayout.addWidget(self.comboBox, 1, Qt.AlignRight)  # type: ignore
        for button in (
            self.pasteButton,
            self.importButton,
            self.clearButton,
            self.deleteButton,
        ):
            self.hBoxLayout.addSpacing(6)
            self.hBoxLayout.addWidget(button)
        self.hBoxLayout.addSpacing(16)

        self._reload_keys()
        self.comboBox.currentTextChanged.connect(self._on_text_changed)
        self.pasteButton.clicked.connect(self._paste_from_clipboard)
        self.importButton.clicked.connect(self._import_from_file)
        self.clearButton.clicked.connect(self._clear_current_text)
        self.deleteButton.clicked.connect(self._delete_current_key)
        keyConfigItem.valueChanged.connect(self.setValue)

    def _stored_keys(self) -> list[str]:
        raw = qconfig.get(self.keysConfigItem) or "[]"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [str(item).strip() for item in data if str(item).strip()]

    def _save_keys(self, keys: list[str]):
        unique_keys = list(dict.fromkeys(key.strip() for key in keys if key.strip()))
        qconfig.set(self.keysConfigItem, json.dumps(unique_keys, ensure_ascii=False))

    def _reload_keys(self):
        current_key = (qconfig.get(self.keyConfigItem) or "").strip()
        keys = self._stored_keys()
        if current_key and current_key not in keys:
            keys.insert(0, current_key)
            self._save_keys(keys)

        self._updating = True
        self.comboBox.clear()
        self.comboBox.addItems(keys)
        self.comboBox.setText(current_key)
        self._updating = False

    def _remember_key(self, key: str):
        key = key.strip()
        if not key:
            return
        keys = self._stored_keys()
        if key not in keys:
            keys.insert(0, key)
            self._save_keys(keys)
            self._reload_keys()

    def _on_text_changed(self, text: str):
        if self._updating:
            return
        key = text.strip()
        qconfig.set(self.keyConfigItem, key)
        if key:
            self._remember_key(key)
        self.keyChanged.emit(key)

    def setValue(self, value: str):
        value = (value or "").strip()
        if self.comboBox.currentText() == value:
            return
        self._updating = True
        self.comboBox.setText(value)
        self._updating = False
        if value:
            self._remember_key(value)

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            self.comboBox.setText(clipboard.text().strip())

    def _import_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("导入 API Key"),
            "",
            self.tr("文本文件 (*.txt);;所有文件 (*)"),
        )
        if not file_path:
            return
        text = Path(file_path).read_text(encoding="utf-8").strip()
        # Allow one key per line and select the first imported key.
        keys = [line.strip() for line in text.splitlines() if line.strip()]
        if not keys:
            return
        merged = keys + self._stored_keys()
        self._save_keys(merged)
        self._reload_keys()
        self.comboBox.setText(keys[0])

    def _clear_current_text(self):
        self.comboBox.setText("")

    def _delete_current_key(self):
        current_key = self.comboBox.currentText().strip()
        if not current_key:
            return
        keys = [key for key in self._stored_keys() if key != current_key]
        self._save_keys(keys)
        self._reload_keys()
        next_key = keys[0] if keys else ""
        self.comboBox.setText(next_key)
