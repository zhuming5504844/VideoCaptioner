"""DeepInfra 转录设置组件"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    ComboBoxSettingCard,
    RangeSettingCard,
    SettingCardGroup,
    SingleDirectionScrollArea,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.asr.deepinfra_asr import DEEPINFRA_MODELS
from videocaptioner.core.entities import TranscribeLanguageEnum

from ..common.config import cfg
from .ApiKeyComboSettingCard import ApiKeyComboSettingCard
from .EditComboBoxSettingCard import EditComboBoxSettingCard


class DeepInfraSettingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        self.scrollArea = SingleDirectionScrollArea(orient=Qt.Vertical, parent=self)
        self.scrollArea.setStyleSheet(
            "QScrollArea{background: transparent; border: none}"
        )

        self.container = QWidget(self)
        self.container.setStyleSheet("QWidget{background: transparent}")
        self.containerLayout = QVBoxLayout(self.container)

        self.setting_group = SettingCardGroup(self.tr("DeepInfra 设置"), self)

        self.api_key_card = ApiKeyComboSettingCard(
            cfg.deepinfra_api_key,
            cfg.deepinfra_api_keys,
            FIF.FINGERPRINT,
            self.tr("API Key"),
            self.tr(
                "输入、粘贴或手动切换 DeepInfra API Key（也支持 DEEPINFRA_API_KEY 环境变量）"
            ),
            self.setting_group,
        )

        model_labels = [f"{k} - {v}" for k, v in DEEPINFRA_MODELS.items()]
        self.model_card = EditComboBoxSettingCard(
            cfg.deepinfra_model,
            FIF.ROBOT,
            self.tr("DeepInfra 模型"),
            self.tr(
                "选择 DeepInfra 语音识别模型，或直接输入 DeepInfra 最新/自定义模型名"
            ),
            model_labels,
            self.setting_group,
        )

        self.language_card = ComboBoxSettingCard(
            cfg.transcribe_language,
            FIF.LANGUAGE,
            self.tr("源语言"),
            self.tr("音视频中说话的语言，留空则自动检测"),
            [lang.value for lang in TranscribeLanguageEnum],
            self.setting_group,
        )

        self.task_card = ComboBoxSettingCard(
            cfg.deepinfra_task,
            FIF.SEND,
            self.tr("任务类型"),
            self.tr(
                "transcribe 为转录原语言；translate 会尝试翻译为英文（模型支持时生效）"
            ),
            ["transcribe", "translate"],
            self.setting_group,
        )

        self.temperature_card = RangeSettingCard(
            cfg.deepinfra_temperature,
            FIF.SPEED_HIGH,
            self.tr("采样温度"),
            self.tr("默认 0 更稳定；调高可能增加随机性"),
            self.setting_group,
        )

        self.api_key_card.comboBox.setMinimumWidth(260)
        self.model_card.comboBox.setMinimumWidth(320)
        self.language_card.comboBox.setMinimumWidth(200)
        self.task_card.comboBox.setMinimumWidth(160)

        self.setting_group.addSettingCard(self.api_key_card)
        self.setting_group.addSettingCard(self.model_card)
        self.setting_group.addSettingCard(self.language_card)
        self.setting_group.addSettingCard(self.task_card)
        self.setting_group.addSettingCard(self.temperature_card)

        self.containerLayout.addWidget(self.setting_group)
        self.containerLayout.addStretch(1)

        self.scrollArea.setWidget(self.container)
        self.scrollArea.setWidgetResizable(True)

        self.main_layout.addWidget(self.scrollArea)
