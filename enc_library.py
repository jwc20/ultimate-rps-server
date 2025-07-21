import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class EncLibrary:
    def __init__(self):
        self._pair_key = self._get_pair_key()

    def _get_pair_key(self):
        """Returns the pair key arrays for substitution cipher"""
        pair_key = [[], []]

        pair_key[0] = [
            'A', 'd', 'K', 'a', '!', '6', 'y', 'r', '7', 'M', ')',
            '(', 'z', 'U', '`', '{', 'V', '[', '#', 'f', '1', '8',
            ':', 'o', 'x', '@', 'L', 'R', 'G', '%', '&', '^', ';',
            'P', '=', 'e', '}', 'i', 'D', 'T', 's', 'S', '>', '-',
            '/', ',', '+', '<', 'v', ']', 't', '~', 'C', 'u', '$',
            'N', '_', 'j', '*', '?', 'c', 'q', '.', 'J', 'O'
        ]

        pair_key[1] = [
            'O', 'N', 'L', 'Y', 'b', 'y', 'G', 'R', 'A', 'C', 'E',
            'j', 'Q', 'g', 'w', 'B', 'h', 'x', 'S', 'i', 'D', 'T',
            'z', 'U', 'k', '0', 'F', 'V', 'l', '1', 'W', 'm', '2',
            'H', 'X', 'n', '3', 'I', 'o', '4', 'J', 'Z', 'p', '5',
            'K', 'a', 'q', '6', 'r', '7', 'M', 'c', 's', '8', 'd',
            't', '9', 'e', 'u', '+', 'P', 'f', 'v', '/', '='
        ]

        return pair_key

    def base64_enc(self, value, encoding='utf-8'):
        """Base64 encode a string"""
        if value is None:
            return ''

        byte_data = value.encode(encoding)
        return base64.b64encode(byte_data).decode('ascii')

    def base64_dec(self, value, encoding='utf-8'):
        """Base64 decode a string"""
        if value is None:
            return ''

        byte_data = base64.b64decode(value)
        return byte_data.decode(encoding)

    def two_way_enc(self, value):
        """Two-way encryption using character substitution"""
        if not value or value.isspace():
            return ''

        base64_text = self.base64_enc(value)
        result = []

        for char in base64_text:
            try:
                idx = self._pair_key[1].index(char)
                result.append(self._pair_key[0][idx])
            except ValueError:
                result.append(char)

        return ''.join(result)

    def two_way_dec(self, value):
        """Two-way decryption using character substitution"""
        if not value or value.isspace():
            return ''

        result = []

        for char in value:
            try:
                idx = self._pair_key[0].index(char)
                result.append(self._pair_key[1][idx])
            except ValueError:
                result.append(char)

        base64_text = ''.join(result)
        return self.base64_dec(base64_text)

    def two_way_enc_aes(self, key, value):
        """Two-way encryption using AES"""
        # Prepare key - truncate or pad to 16 bytes
        key_bytes = key.encode('utf-8')
        if len(key_bytes) > 16:
            key_bytes = key_bytes[:16]
        else:
            key_bytes = key_bytes.ljust(16, b'\0')

        # Create cipher with CBC mode
        cipher = AES.new(key_bytes, AES.MODE_CBC, key_bytes)

        # Pad plaintext and encrypt
        plaintext = value.encode('utf-8')
        padded_plaintext = pad(plaintext, AES.block_size, style='pkcs7')
        ciphertext = cipher.encrypt(padded_plaintext)

        return base64.b64encode(ciphertext).decode('ascii')

    def two_way_dec_aes(self, key, value):
        """Two-way decryption using AES"""
        try:
            # Prepare key - truncate or pad to 16 bytes
            key_bytes = key.encode('utf-8')
            if len(key_bytes) > 16:
                key_bytes = key_bytes[:16]
            else:
                key_bytes = key_bytes.ljust(16, b'\0')

            # Create cipher with CBC mode
            cipher = AES.new(key_bytes, AES.MODE_CBC, key_bytes)

            # Decode base64 and decrypt
            ciphertext = base64.b64decode(value)
            padded_plaintext = cipher.decrypt(ciphertext)
            plaintext = unpad(padded_plaintext, AES.block_size, style='pkcs7')

            return plaintext.decode('utf-8')
        except Exception:
            return ''

    def one_way_enc(self, value):
        """One-way encryption using SHA1"""
        sha1 = hashlib.sha1()
        sha1.update(value.encode('utf-8'))
        return base64.b64encode(sha1.digest()).decode('ascii')

    def wd_enc(self, value):
        """Custom encoding function"""
        if not value or value.isspace():
            return ''

        result = []

        for char in value:
            # Get ASCII code
            c_code = ord(char)
            # Apply transformation
            c_code = (c_code + 73) % 256
            result.append(str(c_code))

        return ' '.join(result)


# Example usage:
if __name__ == "__main__":
    enc = EncLibrary()

    # Test base64 encoding/decoding
    test_string = "Hello, World!"
    encoded = enc.base64_enc(test_string)
    decoded = enc.base64_dec(encoded)
    print(f"Base64 - Original: {test_string}")
    print(f"Base64 - Encoded: {encoded}")
    print(f"Base64 - Decoded: {decoded}")
    print()

    # Test character substitution encryption/decryption
    encrypted = enc.two_way_enc(test_string)
    decrypted = enc.two_way_dec(encrypted)
    print(f"Substitution - Original: {test_string}")
    print(f"Substitution - Encrypted: {encrypted}")
    print(f"Substitution - Decrypted: {decrypted}")
    print()

    # Test AES encryption/decryption
    key = "MySecretKey123"
    aes_encrypted = enc.two_way_enc_aes(key, test_string)
    aes_decrypted = enc.two_way_dec_aes(key, aes_encrypted)
    print(f"AES - Original: {test_string}")
    print(f"AES - Encrypted: {aes_encrypted}")
    print(f"AES - Decrypted: {aes_decrypted}")
    print()

    # Test SHA1 hashing
    hashed = enc.one_way_enc(test_string)
    print(f"SHA1 - Original: {test_string}")
    print(f"SHA1 - Hashed: {hashed}")
    print()

    # Test WD encoding
    wd_encoded = enc.wd_enc(test_string)
    print(f"WD - Original: {test_string}")
    print(f"WD - Encoded: {wd_encoded}")
    
    