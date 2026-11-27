"""AppContext - builds every service once and wires them together, following
the collaboration class diagram (Figure 1 of the design report)."""
from __future__ import annotations

from .ai.biometric import BiometricEngine
from .ai.camera import Camera
from .ai.covers import CoverIndex
from .ai.llm_client import LLMClient
from .ai.rag import RAGRetriever
from .config import Config
from .persistence.filestore import FileStore
from .services.admin_service import AdminService
from .services.auth_service import AuthService
from .services.catalog_service import CatalogService
from .services.chatbot_service import ChatbotService
from .services.purchase_service import PurchaseService
from .services.reading_companion import ReadingCompanion
from .services.recommendation_engine import RecommendationEngine
from .services.review_service import (ModerationEngine, RatingService, ReviewService,
                                      TabooService, WarningService)
from .services.base import Users
from .services.status_manager import StatusManager
from .services.wallet_service import WalletService


class AppContext:
    def __init__(self, config: Config | None = None, biometric: BiometricEngine | None = None,
                 llm: LLMClient | None = None, camera: Camera | None = None):
        self.config = cfg = config or Config()
        self.store = FileStore(cfg.data_dir)
        self.store.ensure_files()
        self.users = Users(self.store)

        # entity/AI components
        self.biometric = biometric or BiometricEngine(cfg.models_dir, cfg.face_detector_file,
                                                      cfg.face_embedder_file, cfg.face_threshold,
                                                      cfg.face_detect_conf)
        self.camera = camera or Camera(cfg.camera_index)
        self.covers = CoverIndex(cfg.covers_dir / "index")
        self.rag = RAGRetriever(self.store)
        self.llm = llm or LLMClient(cfg.ollama_url, cfg.ollama_model, cfg.llm_timeout_s)

        # control classes
        self.status = StatusManager(self.store, cfg)
        self.wallet = WalletService(self.store, cfg)
        self.auth = AuthService(self.store, cfg, self.biometric)
        self.catalog = CatalogService(self.store, cfg, self.covers, self.rag)
        self.recs = RecommendationEngine(self.store, cfg)
        self.purchases = PurchaseService(self.store, cfg, self.wallet, self.status)
        self.taboo = TabooService(self.store, cfg)
        self.moderation = ModerationEngine(cfg.taboo_block_over)
        self.ratings = RatingService(self.store, cfg)
        self.warnings = WarningService(self.store, cfg, self.status)
        self.reviews = ReviewService(self.store, cfg, self.taboo, self.moderation, self.ratings, self.warnings)
        self.admin = AdminService(self.store, cfg, self.status, self.wallet)
        self.chatbot = ChatbotService(self.store, cfg, self.rag, self.llm, self.admin, self.recs)
        self.companion = ReadingCompanion(self.store, cfg, self.catalog, self.purchases, self.rag, self.llm)

    def startup(self) -> None:
        """Index any book whose cover/text was not indexed yet (UC-15 alternative flow)."""
        self.catalog.index_pending()
