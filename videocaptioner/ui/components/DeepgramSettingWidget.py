"""Deepgram 转录设置组件"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBoxSettingCard,
    SettingCardGroup,
    SingleDirectionScrollArea,
    SwitchSettingCard,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.asr.deepgram_asr import DEEPGRAM_MODELS
from videocaptioner.core.entities import TranscribeLanguageEnum

from ..common.config import cfg
from .ApiKeyComboSettingCard import ApiKeyComboSettingCard


class DeepgramSettingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        # 创建单向滚动区域和容器
        self.scrollArea = SingleDirectionScrollArea(orient=Qt.Vertical, parent=self)
        self.scrollArea.setStyleSheet(
            "QScrollArea{background: transparent; border: none}"
        )

        self.container = QWidget(self)
        self.container.setStyleSheet("QWidget{background: transparent}")
        self.containerLayout = QVBoxLayout(self.container)

        self.setting_group = SettingCardGroup(self.tr("Deepgram 设置"), self)

        # API Key
        self.api_key_card = ApiKeyComboSettingCard(
            cfg.deepgram_api_key,
            cfg.deepgram_api_keys,
            FIF.FINGERPRINT,
            self.tr("API Key"),
            self.tr("输入、粘贴、导入或手动切换 Deepgram API Key（也支持 DEEPGRAM_API_KEY 环境变量）"),
            self.setting_group,
        )

        # Model
        model_labels = [f"{k} - {v}" for k, v in DEEPGRAM_MODELS.items()]
        self.model_card = ComboBoxSettingCard(
            cfg.deepgram_model,
            FIF.ROBOT,
            self.tr("Deepgram 模型"),
            self.tr("选择 Deepgram 转录模型"),
            model_labels,
            self.setting_group,
        )

        # Language
        self.language_card = ComboBoxSettingCard(
            cfg.transcribe_language,
            FIF.LANGUAGE,
            self.tr("源语言"),
            self.tr("音视频中说话的语言，留空则自动检测"),
            [lang.value for lang in TranscribeLanguageEnum],
            self.setting_group,
        )

        # Punctuate
        self.punctuate_card = SwitchSettingCard(
            FIF.EDIT,
            self.tr("自动标点"),
            self.tr("自动添加标点和首字母大写"),
            cfg.deepgram_punctuate,
            self.setting_group,
        )

        # Smart Format
        self.smart_format_card = SwitchSettingCard(
            FIF.DEVELOPER_TOOLS,
            self.tr("智能格式化"),
            self.tr("对数字、金额、日期等自动格式化"),
            cfg.deepgram_smart_format,
            self.setting_group,
        )

        # Diarize
        self.diarize_card = SwitchSettingCard(
            FIF.PEOPLE,
            self.tr("说话人分离"),
            self.tr("识别不同说话人并分别标记"),
            cfg.deepgram_diarize,
            self.setting_group,
        )

        # 设置最小宽度
        self.api_key_card.comboBox.setMinimumWidth(310)
        self.model_card.comboBox.setMinimumWidth(200)
        self.language_card.comboBox.setMinimumWidth(200)

        # 添加所有卡片到组
        self.setting_group.addSettingCard(self.api_key_card)
        self.setting_group.addSettingCard(self.model_card)
        self.setting_group.addSettingCard(self.language_card)
        self.setting_group.addSettingCard(self.punctuate_card)
        self.setting_group.addSettingCard(self.smart_format_card)
        self.setting_group.addSettingCard(self.diarize_card)

        # 将设置组添加到容器布局
        self.containerLayout.addWidget(self.setting_group)
        self.containerLayout.addStretch(1)

        # 设置滚动区域
        self.scrollArea.setWidget(self.container)
        self.scrollArea.setWidgetResizable(True)

        # 将滚动区域添加到主布局
        self.main_layout.addWidget(self.scrollArea)
