
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# Create the directory if it doesn't exist
keys_dir = Path(".secrets/paseto")
keys_dir.mkdir(parents=True, exist_ok=True)

# Generate Ed25519 key pair
private_key = ed25519.Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# Save private key
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
private_key_path = keys_dir / "private.pem"
with open(private_key_path, "wb") as f:
    f.write(private_pem)

# Save public key
public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)
public_key_path = keys_dir / "public.pem"
with open(public_key_path, "wb") as f:
    f.write(public_pem)

print(f"PASETO keys generated successfully!")
print(f"Private key: {private_key_path}")
print(f"Public key: {public_key_path}")

