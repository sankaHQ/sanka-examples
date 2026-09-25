# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Parent(Base):
    __tablename__ = "parents"
    widgets: Mapped[list["Widget"]] = relationship(back_populates="parent")
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    count: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)


class Widget(Base):
    __tablename__ = "widgets"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    parent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("parents.id"), index=True
    )
    parent: Mapped[Parent] = relationship(back_populates="widgets")
    enabled: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)
