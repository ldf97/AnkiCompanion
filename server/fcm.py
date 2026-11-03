"""Best-effort Firebase Cloud Messaging wakeups for paired Android devices."""
from datetime import timedelta
from pathlib import Path
from queue import Queue
from threading import Thread
import logging
import os

logger = logging.getLogger(__name__)

class FcmDispatcher:
    def __init__(self, store, data_dir, send=None):
        self.store = store
        self.path = Path(os.environ.get('ANKI_COMPANION_FIREBASE_CREDENTIALS')
                         or Path(data_dir) / 'firebase-service-account.json')
        self._send = send
        self.configured = bool(send) or self.path.is_file()
        self.last_error = ''
        self.last_success = False
        self._client = None
        self._queue = Queue(maxsize=2048)
        self._started = False
        if self.configured:
            self._start()

    def _start(self):
        if not self._started:
            self._started = True
            Thread(target=self._worker, daemon=True, name='AnkiCompanion-FCM').start()

    def reload(self):
        self._client = None
        self.configured = bool(self._send) or self.path.is_file()
        if self.configured:
            self._start()
        return self.status()

    def status(self):
        return {'configured': self.configured,
                'last_success': self.last_success, 'last_error': self.last_error,
                'registered_devices': self.store.push_count()}

    def publish(self, changes):
        if not self.configured:
            return
        for change in changes:
            for peer in self.store.push_targets(change):
                try:
                    self._queue.put_nowait((peer['token'], peer['device_id'],
                                           change['collection'], change['seq']))
                except Exception:
                    logger.warning('FCM hint queue full; periodic catchup will recover')
                    return

    def test(self, device_id):
        if not self.configured:
            return False
        peer = self.store.push_token(device_id)
        if peer is None:
            return False
        self._queue.put_nowait((peer['fcm_token'], device_id,
                                peer['collection_id'], 0))
        return True

    def _sender(self):
        if self._send is not None:
            return self._send
        from firebase_admin import credentials, get_app, initialize_app, messaging
        try:
            app = get_app('ankicompanion-push')
        except ValueError:
            app = initialize_app(credentials.Certificate(str(self.path)),
                                 name='ankicompanion-push')

        def send(token, collection, sequence):
            # Data contains only a change hint, not review contents.
            return messaging.send(messaging.Message(
                token=token,
                data={'kind':'anki_changed', 'collection_id':collection,
                      'sequence':str(sequence)},
                android=messaging.AndroidConfig(
                    priority='normal', collapse_key='ankicompanion_sync',
                    ttl=timedelta(hours=1))), app=app)
        return send

    def _worker(self):
        while True:
            token, device, collection, sequence = self._queue.get()
            try:
                if self._client is None:
                    self._client = self._sender()
                self._client(token, collection, sequence)
                self.last_success = True
                self.last_error = ''
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.warning('FCM notification failed: %s', self.last_error)
                if self.last_error in ('UnregisteredError', 'SenderIdMismatchError'):
                    self.store.remove_push_token(device, token)
            finally:
                self._queue.task_done()
