import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from workbench.gallery import EncryptedGallery


class GalleryTests(unittest.TestCase):
    def test_encrypts_image_and_index_and_exports_plain_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            gallery = EncryptedGallery(folder, Fernet.generate_key())
            item = gallery.save_image(b"image-data", {"seed": 123})
            self.assertEqual(gallery.image_bytes(item.id), b"image-data")
            self.assertNotIn(b"image-data", (Path(folder) / item.file_name).read_bytes())
            self.assertNotIn(b"seed", (Path(folder) / "index.enc").read_bytes())
            output = Path(folder) / "export.png"; gallery.export(item.id, output)
            self.assertEqual(output.read_bytes(), b"image-data")
