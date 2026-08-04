# Data retention and deletion

## Scope and authority

The repository defines no automatic retention period. The organization must set one for its jurisdiction, engagement terms and legal-hold obligations. Only an `admin` may purge an uploaded original, and the API requires the active session CSRF token, the current administrator password and a specific reason of at least 12 characters.

## Original-byte purge

Before deletion, test3 resolves the UUID storage path beneath the configured upload root and verifies both byte length and SHA-256 against the document record. The file is moved to a private same-volume staging path, then the database tombstone and append-only `document_purges` event are written in an immediate transaction and the staged bytes are unlinked. An exception attempts to restore the staged file before the database transaction can commit.

The retained tombstone includes the original name, content hash, size, MIME, uploader, timestamps, purge actor/reason and processing provenance. Governed extracted values, decisions, findings and hash-chained audit history are intentionally retained. Retrieval returns HTTP 410. The UI labels the document as purged and cannot repeat the operation.

## Critical limitation

Original-byte purge is not full-case erasure. It does not alter:

- extracted text or normalized values in SQLite;
- append-only review decisions, findings or audit events;
- filesystem snapshots, OS recovery artifacts or storage-device remanence;
- any backup archive created before the purge.

This limitation is explicit because modifying immutable governance history would invalidate its integrity evidence. A legal hold must block operator use of the purge control.

## Full-case destruction

When authorized full erasure is required, stop test3, identify and verify the exact configured data directory, retain any legally required destruction authorization outside the application, and use the organization's approved OS/storage destruction procedure for that directory and every backup copy. Do not reuse or broadly target a home, repository or workspace directory. Then initialize a new empty data directory if operation must continue. test3 does not claim secure physical-media erasure.

## Recovery and evidence

Purged originals are not recoverable through test3. A pre-purge backup may restore them and therefore remains sensitive and subject to the same retention decision. The append-only purge event and hash-chained audit event provide application evidence; they are not a substitute for legal advice or an external records-management system.
