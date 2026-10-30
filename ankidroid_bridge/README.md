# AnkiDroid Companion edition

An auditable extension against AnkiDroid **v2.25.3**, exact upstream commit `d9bf072f814a0c37d30a694192593b31ff2df875`. `apply.py` refuses another revision or a second application. It adds a permission-protected review-history API and native collection sync hooks. It does not write scheduling SQL or alter personal skin assets.

The application ID is `com.ichi2.anki.companion` (debug adds `.debug`) so it installs alongside stock AnkiDroid without replacing its signing identity or local collection. Use the same AnkiWeb account and finish initial collection sync once. The provider's read/write permission remains required. The bridge must then be enabled from AnkiCompanion.

The native Anki backend performs scheduling merges. Review history is exposed as read-only snapshots in bounded pages. Native sync runs before the next question and on activity transitions. Full upload/download conflicts are surfaced for explicit direction choice; the bridge does not overwrite collections to resolve them.

This directory and its patches are GPL-3.0-or-later, matching upstream. Upstream source: https://github.com/ankidroid/Anki-Android/tree/d9bf072f814a0c37d30a694192593b31ff2df875 . Build with JDK 21 and Android SDK 36 after applying the overlay. Check the saved CI evidence for the latest actual build/test status; code presence does not imply device verification.
