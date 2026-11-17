"""Exercise the firmware C frame decoder against the Python wire codec."""
import ctypes
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from ice import Decoder, encode, validate_image


class Rx(ctypes.Structure):
    _fields_=[('bytes',ctypes.c_uint8*268),('used',ctypes.c_uint16),
              ('active',ctypes.c_uint8),('escape',ctypes.c_uint8)]


class WireProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        binary=Path(cls.temp.name)/'protocol.so'
        subprocess.run(['cc','-shared','-fPIC','-std=c11','-Wall','-Wextra','-Werror',
                        str(ROOT/'firmware/dispatcher/protocol.c'),'-o',str(binary)],check=True)
        cls.lib=ctypes.CDLL(str(binary))
        cls.callback=ctypes.CFUNCTYPE(None,ctypes.c_uint8,ctypes.c_uint16,
                                    ctypes.POINTER(ctypes.c_uint8),ctypes.c_uint16,ctypes.c_uint32)
        cls.lib.protocol_byte.argtypes=[ctypes.POINTER(Rx),ctypes.c_uint8,cls.callback]
        cls.lib.protocol_encode.argtypes=[ctypes.c_uint8,ctypes.c_uint16,ctypes.c_uint16,
                                        ctypes.c_void_p,ctypes.c_uint16,ctypes.c_void_p]
        cls.lib.protocol_encode.restype=ctypes.c_size_t

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def decode_c(self,data):
        frames=[]
        callback=self.callback(lambda op,seq,p,n,crc:frames.append((op,seq,bytes(p[:n]))))
        rx=Rx()
        for b in data:self.lib.protocol_byte(ctypes.byref(rx),b,callback)
        return frames

    def test_all_bytes_and_fragmentation(self):
        payload=bytes(range(256))
        self.assertEqual(self.decode_c(encode(13,65535,payload)),[(13,65535,payload)])
        decoder=Decoder();frames=[]
        for b in encode(0x8d,65535,payload):frames+=decoder.feed(bytes([b]))
        self.assertEqual(frames,[(0x8d,65535,0,payload)])

    def test_c_response_matches_python(self):
        payload=bytes([255])*256
        out=ctypes.create_string_buffer(540)
        size=self.lib.protocol_encode(0x89,255,0,payload,256,out)
        self.assertEqual(out.raw[:size],encode(0x89,255,payload))

    def test_corruption_overflow_and_resynchronization(self):
        good=encode(1,7)
        bad=bytearray(encode(5,8));bad[4]^=1
        stream=b'noise'+bytes(bad)+b'\xff\x00'+b'X'*800+b'\xff\x01'+good
        self.assertEqual(self.decode_c(stream),[(1,7,b'')])

    def test_partial_abort_and_new_start(self):
        good=encode(6,9)
        for prefix in (b'\xff\x00abc\xff\x02',encode(5,8)[:-3],b'\xff\x00abc\xff\x03'):
            self.assertEqual(self.decode_c(prefix+good),[(6,9,b'')])

    def test_bad_version_status_and_length_rejected(self):
        for offset,value in ((0,2),(6,1),(4,255)):
            raw=bytearray(struct.pack('<BBHHH',1,5,10,0,0))
            raw[offset]=value
            raw+=struct.pack('<I',zlib.crc32(raw))
            frame=b'\xff\x00'+bytes(raw).replace(b'\xff',b'\xff\xff')+b'\xff\x01'
            self.assertEqual(self.decode_c(frame),[])

    def test_module_header_and_crc(self):
        code=b'\x70\x47'
        image=struct.pack('<7I',0x41505031,2,2,0x20030000,1,2,zlib.crc32(code))+code
        self.assertEqual(validate_image(image),2)
        cpu=struct.pack('<7I',0x41505031,2,6,0x20030000,1,2,zlib.crc32(code))+code
        self.assertEqual(validate_image(cpu),6)
        abc=struct.pack('<7I',0x41505031,2,7,0x20030000,1,2,zlib.crc32(code))+code
        self.assertEqual(validate_image(abc),7)
        unknown=struct.pack('<7I',0x41505031,2,8,0x20030000,1,2,zlib.crc32(code))+code
        with self.assertRaises(ValueError):validate_image(unknown)
        for corrupt in (image[:-1],image[:-1]+b'\x00',b'\x00'+image[1:]):
            with self.assertRaises(ValueError):validate_image(corrupt)
        old=struct.pack('<7I',0x41505031,1,2,0x20040000,1,2,zlib.crc32(code))+code
        with self.assertRaises(ValueError):validate_image(old)


if __name__=='__main__':unittest.main()
