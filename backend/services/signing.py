import os
import io
import json
import base64
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import qrcode

from backend.config import settings

logger = logging.getLogger("transmute.signing")

class SigningService:
    """
    T9 Cryptographic Signing, Watermarking & Tamper-Detection Service.
    Uses Ed25519 for high-speed, modern asymmetric digital signatures
    over SHA-256 canonical digests, with pluggable encrypted keystore and QR generation.
    """

    def __init__(self, keys_dir: Optional[Path] = None):
        self.keys_dir = Path(keys_dir or settings.KEYS_DIR)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.master_key = self._load_or_create_master_key()
        self.active_key_id = self._init_keystore()

    def _load_or_create_master_key(self) -> bytes:
        """
        Retrieves or derives a 256-bit AES-GCM master key used to encrypt private keys at rest.
        Priority:
        1. settings.SIGNING_MASTER_KEY environment variable.
        2. .master.key file in keys directory with restricted permissions.
        """
        env_key = settings.SIGNING_MASTER_KEY.strip()
        if env_key:
            return hashlib.sha256(env_key.encode("utf-8")).digest()

        master_file = self.keys_dir / ".master.key"
        if master_file.exists():
            try:
                with open(master_file, "rb") as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Failed to read master key file: {e}")

        # Generate new random 32-byte master key
        key = AESGCM.generate_key(bit_length=256)
        try:
            with open(master_file, "wb") as f:
                f.write(key)
            os.chmod(master_file, 0o600)
        except Exception as e:
            logger.warning(f"Could not persist master key file with 0600 permissions: {e}")
        return key

    def _encrypt_bytes(self, data: bytes) -> bytes:
        aesgcm = AESGCM(self.master_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def _decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(self.master_key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def _init_keystore(self) -> str:
        """
        Initializes the keystore index and ensures at least one active Ed25519 keypair exists.
        """
        index_file = self.keys_dir / "keys_index.json"
        index: Dict[str, Any] = {"active_key_id": "", "keys": {}}

        if index_file.exists():
            try:
                with open(index_file, "r") as f:
                    index = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading keys_index.json: {e}")

        active_id = index.get("active_key_id")
        if not active_id or active_id not in index.get("keys", {}):
            active_id = self.generate_keypair("transmute-key-2026-v1")
        return active_id

    def generate_keypair(self, key_id: Optional[str] = None) -> str:
        """
        Generates a new Ed25519 keypair, stores private key AES-GCM encrypted,
        stores public key in standard PEM format, and registers it as the active key.
        """
        if not key_id:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            key_id = f"transmute-key-{now_str}"

        private_key = ed25519.Ed25519PrivateKey.generate()
        priv_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        encrypted_priv = self._encrypt_bytes(priv_bytes)

        public_key = private_key.public_key()
        pub_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        pub_raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        pub_b64 = base64.b64encode(pub_raw).decode("ascii")

        # Save private key encrypted
        priv_file = self.keys_dir / f"{key_id}.enc"
        with open(priv_file, "wb") as f:
            f.write(encrypted_priv)
        try:
            os.chmod(priv_file, 0o600)
        except Exception:
            pass

        # Save public key PEM
        pub_file = self.keys_dir / f"{key_id}.pub"
        with open(pub_file, "w") as f:
            f.write(pub_pem)

        # Update index
        index_file = self.keys_dir / "keys_index.json"
        index = {"active_key_id": key_id, "keys": {}}
        if index_file.exists():
            try:
                with open(index_file, "r") as f:
                    index = json.load(f)
            except Exception:
                pass

        index["active_key_id"] = key_id
        index.setdefault("keys", {})[key_id] = {
            "key_id": key_id,
            "algorithm": "Ed25519",
            "public_key_b64": pub_b64,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }

        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)

        self.active_key_id = key_id
        logger.info(f"Generated and activated Ed25519 key: {key_id}")
        return key_id

    def load_private_key(self, key_id: Optional[str] = None) -> ed25519.Ed25519PrivateKey:
        kid = key_id or self.active_key_id
        priv_file = self.keys_dir / f"{kid}.enc"
        if not priv_file.exists():
            raise FileNotFoundError(f"Private key file for {kid} not found.")

        with open(priv_file, "rb") as f:
            encrypted_data = f.read()

        raw_priv = self._decrypt_bytes(encrypted_data)
        return ed25519.Ed25519PrivateKey.from_private_bytes(raw_priv)

    def load_public_key(self, key_id: str) -> ed25519.Ed25519PublicKey:
        pub_file = self.keys_dir / f"{key_id}.pub"
        if not pub_file.exists():
            raise FileNotFoundError(f"Public key file for {key_id} not found.")

        with open(pub_file, "r") as f:
            pem_data = f.read().encode("utf-8")

        return serialization.load_pem_public_key(pem_data)

    def get_public_key_pem(self, key_id: str) -> Optional[str]:
        pub_file = self.keys_dir / f"{key_id}.pub"
        if not pub_file.exists():
            return None
        with open(pub_file, "r") as f:
            return f.read()

    def list_public_keys(self) -> List[Dict[str, Any]]:
        index_file = self.keys_dir / "keys_index.json"
        if not index_file.exists():
            return []
        try:
            with open(index_file, "r") as f:
                index = json.load(f)
            keys_list = []
            for kid, info in index.get("keys", {}).items():
                item = dict(info)
                item["is_active"] = (kid == index.get("active_key_id"))
                keys_list.append(item)
            return keys_list
        except Exception as e:
            logger.warning(f"Error reading keys list: {e}")
            return []

    # -------------------------------------------------------------------------
    # Canonical Hashing & Signing
    # -------------------------------------------------------------------------

    @staticmethod
    def canonicalize(content: str | bytes) -> bytes:
        """
        Normalizes line breaks (\r\n -> \n) and returns standard UTF-8 bytes.
        """
        if isinstance(content, str):
            normalized = content.replace("\r\n", "\n").replace("\r", "\n")
            return normalized.encode("utf-8")
        return content

    @classmethod
    def compute_sha256(cls, content: str | bytes) -> str:
        canonical_bytes = cls.canonicalize(content)
        return hashlib.sha256(canonical_bytes).hexdigest()

    def sign_deliverable(
        self,
        content: str | bytes,
        deliverable_id: str,
        output_type: str,
        revision: int = 1,
        organization: Optional[str] = None,
        tlp_level: Optional[str] = None,
        key_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Computes SHA-256 hash and Ed25519 digital signature over the deliverable content.
        Returns the signed envelope and scannable QR verification URL.
        """
        content_hash = self.compute_sha256(content)
        active_kid = key_id or self.active_key_id
        private_key = self.load_private_key(active_kid)

        # Sign canonical SHA-256 hex digest
        signature_bytes = private_key.sign(content_hash.encode("ascii"))
        sig_b64 = base64.b64encode(signature_bytes).decode("ascii")

        now_iso = datetime.now(timezone.utc).isoformat()
        org = organization or settings.DEFAULT_SIGNING_ORG
        tlp = tlp_level or settings.DEFAULT_TLP_LEVEL

        base_verify_url = settings.VERIFY_BASE_URL.rstrip("/")
        verification_url = f"{base_verify_url}?id={deliverable_id}&hash={content_hash}"

        # Generate QR code data URL (PNG format)
        qr_data_url = self.generate_qr_data_url(verification_url)

        envelope = {
            "format": "transmute-signature-v1",
            "deliverable_id": deliverable_id,
            "revision": revision,
            "output_type": output_type,
            "organization": org,
            "tlp_level": tlp,
            "content_sha256": content_hash,
            "signing_key_id": active_kid,
            "timestamp": now_iso,
            "signature": sig_b64,
            "verification_url": verification_url,
            "qr_data_url": qr_data_url,
        }
        return envelope

    def verify_deliverable(
        self,
        content: Optional[str | bytes] = None,
        signature: Optional[str] = None,
        signing_key_id: Optional[str] = None,
        content_hash: Optional[str] = None,
        expected_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verifies the cryptographic integrity and authenticity of deliverable content.
        Evaluates SHA-256 matching and Ed25519 signature validity.
        """
        computed_hash = None
        if content is not None:
            computed_hash = self.compute_sha256(content)

        # If content_hash is supplied directly (e.g. from envelope or registry)
        target_hash = computed_hash or content_hash
        if not target_hash:
            return {
                "valid": False,
                "status": "INVALID_INPUT",
                "details": "Neither content nor content_hash was provided for verification.",
            }

        # Check expected hash if provided
        if expected_hash and computed_hash and (expected_hash.lower() != computed_hash.lower()):
            return {
                "valid": False,
                "status": "HASH_MISMATCH",
                "computed_hash": computed_hash,
                "expected_hash": expected_hash,
                "details": "Content hash does not match expected hash. Deliverable text has been modified.",
            }

        if not signature or not signing_key_id:
            return {
                "valid": False,
                "status": "MISSING_SIGNATURE",
                "computed_hash": target_hash,
                "details": "Signature or signing_key_id is missing.",
            }

        try:
            pub_key = self.load_public_key(signing_key_id)
        except Exception as e:
            return {
                "valid": False,
                "status": "UNKNOWN_KEY",
                "signing_key_id": signing_key_id,
                "computed_hash": target_hash,
                "details": f"Public key '{signing_key_id}' is unrecognized or revoked: {e}",
            }

        try:
            raw_sig = base64.b64decode(signature)
            # Verify signature against target hash bytes
            pub_key.verify(raw_sig, target_hash.encode("ascii"))
            return {
                "valid": True,
                "status": "AUTHENTIC",
                "signing_key_id": signing_key_id,
                "computed_hash": target_hash,
                "details": "Cryptographically authentic. Signature is valid and content is unmodified.",
            }
        except Exception as e:
            return {
                "valid": False,
                "status": "TAMPERED",
                "signing_key_id": signing_key_id,
                "computed_hash": target_hash,
                "details": f"Signature verification failed: {e}. Content is tampered or forged.",
            }

    @staticmethod
    def generate_qr_data_url(data: str) -> str:
        """
        Generates a PNG QR code data URL from given text/URL.
        """
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=4,
                border=2,
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            b64_img = base64.b64encode(buffered.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64_img}"
        except Exception as e:
            logger.warning(f"Failed to generate QR code: {e}")
            return ""

    @staticmethod
    def generate_sidecar_json(envelope: Dict[str, Any]) -> str:
        """
        Generates pretty formatted JSON sidecar string.
        """
        return json.dumps(envelope, indent=2)

signing_service = SigningService()
