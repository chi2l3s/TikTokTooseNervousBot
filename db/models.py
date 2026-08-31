from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), default="short")
    aspect_ratio: Mapped[str] = mapped_column(String(8), default="9:16")
    face_tracking: Mapped[bool] = mapped_column(Boolean, default=True)
    add_music: Mapped[bool] = mapped_column(Boolean, default=True)
    watermark_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gen_description: Mapped[bool] = mapped_column(Boolean, default=True)
    banner_mode: Mapped[str] = mapped_column(String(32), default="none")
    banner_source_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )