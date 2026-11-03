# AnkiCompanion: free FCM push setup

**Status:** The application code is prepared, but the Firebase project must be created
and the signed Android APK built with its project settings. No Firebase project or
phone has been provisioned by this source change.

## What happens once paired

1. Desktop Anki observes a review and sends the existing authenticated event to the
   **Windows** AnkiCompanion server.
2. That server commits the event to its existing durable SQLite ledger and queues
   an FCM data-only *wake hint* for Android devices in the same collection, except
   the device that created the review. It sends no card content or private data to
   Google; only the collection name and change sequence.
3. Android's `CompanionFcmService` receives the hint and enqueues a **one-off**
   WorkManager sync. This sync reads the authoritative server and native Anki sync
   state before refreshing the widget. The old 15-minute Android JobScheduler job
   remains as offline/reconnect recovery, not as fast polling.
4. The foreground Android app no longer queries the server every five seconds.
   The optional continuous one-second `Live widget updates` button was removed.

## One-time Google console setup (free Spark plan)

1. Open <https://console.firebase.google.com/>, **Create a project** called
   `AnkiCompanion`, disable Analytics if you don't need it, select the **Spark** plan.
   No Firestore database, Cloud Functions, or billing account is required for FCM.
2. Select the **Android app** icon in Project Overview. Android package name is
   **`org.ankicompanion.app`**. Download **`google-services.json`**.
3. **Done (2026-11-03):** The uploaded `google-services.json` has been validated
   against project `ankicompanion` and Android application
   `org.ankicompanion.app`. The Firebase Android *client* configuration is now
   stored as `deployment/firebase/android-client.json`. Both CI and release
   workflows copy it automatically, so no GitHub secret or PowerShell step is
   required for the Android client. Firebase Android API keys identify the
   project, not a privileged Firebase Admin session. The Google API key should
   remain restricted to relevant Firebase APIs. **The separate server-side
   service-account private key must never be committed.**
4. In Firebase console open **Project settings → Service accounts → Generate
   new private key**. Save the downloaded service-account JSON *privately* on
   the Windows machine running the companion server.
5. Once the new Windows version is installed, click **Firebase push** in the
   AnkiCompanion Windows app, select that service-account JSON, and let the app
   install it into its private server data directory. No shell commands required.
   It also asks the server to activate FCM without restarting.
6. From your GitHub repository release workflow, build a **signed** Android
   AnkiCompanion APK with the Firebase secret. Update the phone using the **same
   Android signing certificate** as its currently installed application; a key
   mismatch still needs its separate data-preserving migration.
7. Open the new Android companion once, **Connect** to the Windows server if not
   already paired, and permit network access. It registers its FCM token. In the
   Windows app you can verify the endpoint `GET /v1/push/status` with the existing
   authenticated client; `POST /v1/push/test` with `{"device_id":"android-..."}`
   queues a wake. These endpoints never report an Android delivery acknowledgement.

## Limitations and acceptance

- **Google Play services** is required for standard Android FCM. Offline devices
  catch up via existing durable local history and periodic restart/reconnect sync.
- Delivery can be delayed in Android Doze. Data-only silent messages use normal
  FCM priority to avoid abusing high-priority user-notification channels; there is
  no guaranteed five-second delivery while asleep.
- The PC must be running, its service-account key valid, and the phone must be
  able to reach the existing companion server over its HTTPS connection (the
  Firebase push itself does **not** expose the PC or transfer full reviews).
- The currently installed APK does not gain FCM just because a GitHub source
  branch exists. Install a signed configured build first. The GitHub debug APK
  is NOT a guaranteed in-place replacement for an existing release APK.
- The integration cannot be called *live* until a physical-phone acceptance test
  confirms **PC review → FCM received → WorkManager native sync → widget refreshed**
  without opening the app, including offline/reconnect and locked-screen cases.

## Credentials

`google-services.json` contains the **client configuration** for the Firebase
Android app and is read by the optional Google Services Gradle plugin. The
**service-account JSON is a secret** and stays on the PC at
`%LOCALAPPDATA%/AnkiCompanion/server/firebase-service-account.json`, outside
replaceable binaries and outside the public repository.