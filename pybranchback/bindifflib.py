"""Library for performing binary delta compressions"""
import bsdiff4


def diff(compress, reference):
    """Compresses the given bytes using the reference and return a patch"""
    return bsdiff4.diff(compress, reference)


def patch(patch, reference):
    """Return an uncompressed file by applying the patch to the reference"""
    return bsdiff4.patch(reference, patch)
