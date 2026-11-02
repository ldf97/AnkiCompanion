"""Explain server-reviewed progress and native Anki receipts without false "synced" claims."""


def device_status(device):
    """A scheduling receipt and liveness are independent facts."""
    label=str(device.get('label') or device.get('device_id') or 'Device')[:64]
    revision=device.get('native_sync') or {}
    latest=int(revision.get('revision') or 0)
    applied=int(revision.get('applied_revision') or 0)
    seconds=device.get('age_seconds')
    if device.get('online') is False:
        live=f'offline (last seen {seconds}s ago)' if seconds is not None else 'offline'
    elif device.get('online') is True:
        live='online'
    else:
        live='liveness unknown'
    if latest>applied:
        native=f'Anki sync pending {applied}/{latest}'
    elif latest>0 and applied>=latest:
        native=f'Anki sync confirmed {applied}/{latest}'
    else:
        native='Anki sync not yet verified'
    return f'{label}: {live}; {native}'