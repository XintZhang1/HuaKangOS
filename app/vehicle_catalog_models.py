"""Explicit model hierarchy and staff-confirmed inventory classification."""
from sqlalchemy import ForeignKey,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .master_models import MasterRecord
from .flow_models import Versioned


class VehicleBrand(MasterRecord,Base):
    __tablename__='catalog_vehicle_brands'


class VehicleSeries(MasterRecord,Base):
    __tablename__='catalog_vehicle_series'
    brand_id:Mapped[int]=mapped_column(ForeignKey('catalog_vehicle_brands.id'),index=True)


class ModelClassification(Versioned,Base):
    __tablename__='catalog_model_classifications'
    model_id:Mapped[int]=mapped_column(ForeignKey('master_vehicle_models.id'))
    series_id:Mapped[int]=mapped_column(ForeignKey('catalog_vehicle_series.id'))
    __table_args__=(UniqueConstraint('model_id',name='uq_catalog_model_classification'),)


class VehicleClassification(Versioned,Base):
    __tablename__='catalog_vehicle_classifications'
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'))
    model_id:Mapped[int]=mapped_column(ForeignKey('master_vehicle_models.id'))
    __table_args__=(UniqueConstraint('vehicle_id',name='uq_catalog_vehicle_classification'),)
