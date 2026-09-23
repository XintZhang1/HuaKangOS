"""Read-only current VIN custody and paired internal vehicle balances."""
from collections import defaultdict
from sqlalchemy import select
from .vehicle_transfer_models import VehicleTransfer, VehicleCustody, VehicleTransferSettlement


def availability_flags(db):
    """Only scoped inventory IDs and reasons; never another store's vehicle data."""
    from .vehicle_procurement_models import VehiclePurchaseReceipt,VehiclePurchaseReturn
    ids=tuple(x for x in db.info.get('store_scope',()) if x)
    previous=db.info.get('_transfer_authority');db.info['_transfer_authority']=('report',ids)
    try:
        result={key:'transfer_reserved' for key in db.scalars(select(VehicleCustody.current_vehicle_id).where(
            VehicleCustody.current_store_id.in_(ids),VehicleCustody.current_vehicle_id.is_not(None),VehicleCustody.pending_transfer_id.is_not(None)))}
        query=select(VehiclePurchaseReceipt.vehicle_id).join(VehiclePurchaseReturn,VehiclePurchaseReturn.shipment_id==VehiclePurchaseReceipt.shipment_id).where(VehiclePurchaseReturn.status.in_(['requested','approved']))
        result.update({key:'purchase_return' for key in db.scalars(query)})
        return result
    finally:
        if previous is None:db.info.pop('_transfer_authority',None)
        else:db.info['_transfer_authority']=previous


def current_vehicles(db,user,bounded):
    ids=tuple(x for x in db.info.get('store_scope',()) if x)
    previous=db.info.get('_transfer_authority');db.info['_transfer_authority']=('report',ids)
    try:
        headers=bounded(db,VehicleTransfer,select(VehicleTransfer).where(VehicleTransfer.from_store_id.in_(ids),VehicleTransfer.status.in_(['transit','rejected','return_transit'])))
        pending=set(db.scalars(select(VehicleCustody.current_vehicle_id).where(VehicleCustody.current_store_id.in_(ids),VehicleCustody.pending_transfer_id.is_not(None),VehicleCustody.current_vehicle_id.is_not(None))))
        rows=[dict(id=t.id,case_id=t.from_case_id,number=t.number,from_store_id=t.from_store_id,to_store_id=t.to_store_id,
            vin=t.vin,model=t.snapshot['model'],value_cents=t.snapshot['purchase_cost_cents'],status=t.status) for t in headers]
        clearing=defaultdict(int)
        from .vehicle_transport_models import VehicleTransportLossSettlement,VehicleTransportFoundSettlement
        for model in (VehicleTransferSettlement,VehicleTransportLossSettlement,VehicleTransportFoundSettlement):
            for entry in bounded(db,model):clearing[entry.store_id]+=entry.amount_cents
        return pending,rows,clearing
    finally:
        if previous is None:db.info.pop('_transfer_authority',None)
        else:db.info['_transfer_authority']=previous
