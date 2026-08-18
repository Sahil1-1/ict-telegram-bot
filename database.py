from sqlalchemy import (
    create_engine, Column, Integer, String,
    Float, DateTime, Boolean, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Signal(Base):
    __tablename__ = "signals"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    timestamp     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    signal_type   = Column(String(20))
    symbol        = Column(String(50))
    asset_class   = Column(String(20))
    broker        = Column(String(100))
    crypto_type   = Column(String(20))
    timeframe     = Column(String(20))
    entry         = Column(Float, nullable=True)
    stop_loss     = Column(Float, nullable=True)
    tp1           = Column(Float, nullable=True)
    tp2           = Column(Float, nullable=True)
    rr_tp1        = Column(Float, nullable=True)
    rr_tp2        = Column(Float, nullable=True)
    confidence    = Column(String(50))
    risk_percent  = Column(Float, nullable=True)
    exchange      = Column(String(50))
    raw_json      = Column(Text)
    message_sent  = Column(Boolean, default=False)


class ChatGroup(Base):
    __tablename__ = "chat_groups"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    chat_id     = Column(String(50), unique=True, nullable=False)
    chat_title  = Column(String(200))
    added_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active   = Column(Boolean, default=True)


class Member(Base):
    __tablename__ = "members"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(Integer, unique=True, nullable=False)
    username         = Column(String(100))
    first_name       = Column(String(100))
    joined_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active        = Column(Boolean, default=True)


Base.metadata.create_all(engine)


def save_signal(data: dict, raw_json: str):
    session = SessionLocal()
    try:
        signal = Signal(
            signal_type  = data.get("signal", ""),
            symbol       = data.get("symbol", ""),
            asset_class  = data.get("asset_class", ""),
            broker       = data.get("broker", ""),
            crypto_type  = data.get("crypto_type", ""),
            timeframe    = data.get("timeframe", ""),
            entry        = data.get("entry"),
            stop_loss    = data.get("stop_loss"),
            tp1          = data.get("tp1"),
            tp2          = data.get("tp2"),
            rr_tp1       = data.get("rr_tp1"),
            rr_tp2       = data.get("rr_tp2"),
            confidence   = data.get("confidence", ""),
            risk_percent = data.get("risk_percent"),
            exchange     = data.get("exchange", ""),
            raw_json     = raw_json,
            message_sent = False,
        )
        session.add(signal)
        session.commit()
        session.refresh(signal)
        return signal
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def mark_signal_sent(signal_id: int):
    session = SessionLocal()
    try:
        sig = session.query(Signal).filter_by(id=signal_id).first()
        if sig:
            sig.message_sent = True
            session.commit()
    finally:
        session.close()


def get_active_chat_ids() -> list:
    session = SessionLocal()
    try:
        groups = session.query(ChatGroup).filter_by(is_active=True).all()
        return [g.chat_id for g in groups]
    finally:
        session.close()


def add_chat_group(chat_id: str, chat_title: str = ""):
    session = SessionLocal()
    try:
        existing = session.query(ChatGroup).filter_by(chat_id=chat_id).first()
        if not existing:
            group = ChatGroup(chat_id=chat_id, chat_title=chat_title)
            session.add(group)
            session.commit()
    finally:
        session.close()


def remove_chat_group(chat_id: str):
    session = SessionLocal()
    try:
        group = session.query(ChatGroup).filter_by(chat_id=chat_id).first()
        if group:
            group.is_active = False
            session.commit()
    finally:
        session.close()


def add_member(user_id: int, username: str = "", first_name: str = ""):
    session = SessionLocal()
    try:
        existing = session.query(Member).filter_by(
            telegram_user_id=user_id
        ).first()
        if not existing:
            member = Member(
                telegram_user_id=user_id,
                username=username,
                first_name=first_name,
            )
            session.add(member)
            session.commit()
    finally:
        session.close()


def get_recent_signals(limit: int = 10) -> list:
    session = SessionLocal()
    try:
        return (
            session.query(Signal)
            .order_by(Signal.timestamp.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()
