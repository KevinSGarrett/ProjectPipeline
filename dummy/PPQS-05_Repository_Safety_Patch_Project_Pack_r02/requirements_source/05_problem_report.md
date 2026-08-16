# Corrupt Encrypted Metadata Safety Problem

A repository can contain a key metadata record or configuration metadata record whose encrypted data is shorter than the encryption overhead. The affected read paths currently assume enough bytes exist before separating the nonce and ciphertext. A truncated upload or hostile backend fixture can therefore terminate a command with a bounds failure.

Repair the behavior so every undersized payload is rejected with a clear error before slicing or decryption. Preserve valid-repository behavior, cryptographic verification, authentication, file-format compatibility, and the existing scope of trust. Add focused table-driven regression tests, run formatting and relevant package tests, and create the required unreleased changelog record. Avoid unrelated modernization or dependency changes.
