"""Verify a versioned source collection without executing upstream code.

Collection review is independent of formula execution, economic validation and
commercial rights. Public-clone validation cannot re-fetch private raw evidence.
"""
from bisect import bisect_right
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tarfile
from tempfile import TemporaryFile
from urllib.parse import unquote, urljoin, urlsplit
import zlib

from quantgraph.graph.collection_dedup import collection_source_keys
from quantgraph.graph.metadata_pilot import digest, encoded, read_below, validate


FORMAT = 'quantgraph-source-collection/v1'
SOURCE_FORMAT = 'quantgraph-source-collection-lock/v1'
REVIEW_FORMAT = 'quantgraph-source-collection-reviews/v1'
CORE = {'strategy': ('signal', 'entry', 'exit', 'position'),
        'factor': ('formula', 'inputs', 'calculation')}
CONTENT_ROLES = {'source_code', 'author_document', 'published_definition'}
NO_CREDIT = {'EXISTING_DEFINITION', 'EXACT_DUPLICATE', 'MIRROR_OR_PORT',
             'PARAMETER_ONLY_VARIANT', 'AMBIGUOUS', 'INCOMPLETE'}


def _pin(root, path, pin):
    raw = read_below(root, path)
    if digest(raw) != pin['sha256'] or len(raw) != pin['bytes']:
        raise ValueError('Collection byte pin mismatch: ' + path)
    return raw


def _relative(path):
    return isinstance(path, str) and path and not path.startswith('/') and '\\' not in path and all(
        part not in {'', '.', '..'} for part in path.split('/'))


def _date(value):
    if not isinstance(value, str) or not datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo:
        raise ValueError('Collection evidence requires a timezone-aware timestamp')


def _identity(record):
    return tuple(record[key] for key in ('identity_namespace', 'entity_type', 'record_id'))


PDF_EXTRACTION = 'pdf.pdftotext-layout'
PDF_ARGUMENTS = ['-layout', '-enc', 'UTF-8', '-', '-']
PDF_VISUAL_EXTRACTION = 'pdf.visual-pages/v1'
PDF_VISUAL_ARGUMENTS = ['-singlefile', '-png']
PDF_VISUAL_MAX_BYTES = 8 * 1024 * 1024
PDF_VISUAL_MAX_PIXELS = 16_000_000
TAR_EXTRACTION = 'tar.members-utf8/v1'
IMAGE_EXTRACTION = 'image.visual-page/v1'
IMAGE_MAX_BYTES = 8 * 1024 * 1024
IMAGE_MAX_PIXELS = 16_000_000


def _image_contract(source):
    """Original HTTP images have an HTML identity link, never a PDF parent."""
    image = source.get('original_image')
    if (source['role'] not in {'author_document', 'published_definition'}
            or source['revision_kind'] != 'content_snapshot'
            or not 67 <= source['bytes'] <= IMAGE_MAX_BYTES
            or not _visual_snapshot(source['snapshot_path'])
            or not source['snapshot_path'].endswith('.png')
            or {'derived_text', 'visual_pages', 'archive_members', 'parent_pdf_sha256',
                'renderer', 'generator'} & source.keys()
            or not isinstance(image, dict)
            or set(image) != {'format', 'width', 'height', 'bit_depth', 'color_type',
                              'printed_page', 'identity_link'}):
        raise ValueError('Invalid original image source contract')
    if (image['format'] != 'PNG' or type(image['bit_depth']) is not int or image['bit_depth'] != 4
            or type(image['color_type']) is not int or image['color_type'] != 0
            or any(type(image[k]) is not int or not 1 <= image[k] <= 10_000 for k in ('width', 'height'))
            or image['width'] * image['height'] > IMAGE_MAX_PIXELS
            or not isinstance(image['printed_page'], str)
            or not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z ._-]{0,63}', image['printed_page'])):
        raise ValueError('Unsupported original image dimensions, format or printed page')
    link = image['identity_link']
    if (not isinstance(link, dict)
            or set(link) != {'source_id', 'source_sha256', 'first_line', 'last_line',
                             'sha256', 'tag', 'attribute', 'url', 'attributes'}
            or not isinstance(link['source_id'], str) or not link['source_id']
            or any(not isinstance(link[k], str) or not re.fullmatch(r'[0-9a-f]{64}', link[k])
                   for k in ('source_sha256', 'sha256'))
            or type(link['first_line']) is not int or type(link['last_line']) is not int
            or not 1 <= link['first_line'] <= link['last_line']
            or link['tag'] != 'img' or link['attribute'] != 'src' or link['url'] != source['url']
            or link['attributes'] != dict(alt=image['printed_page'], width=str(image['width']),
                                          height=str(image['height']))):
        raise ValueError('Invalid original image HTML identity link')
    return image


def _verify_original_png(raw, image):
    """Decode only bounded, noninterlaced gray4 scanlines, without an image library.

    This is deliberately narrower than the PDF renderer's PNG checker. Ancillary
    data is never decompressed; IDAT must be exactly one bounded zlib stream.
    """
    if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > IMAGE_MAX_BYTES:
        raise ValueError('Original image is not a bounded PNG')
    offset, header, ended, data_closed = 8, None, False, False
    seen, compressed = set(), bytearray()
    while offset + 12 <= len(raw):
        length = int.from_bytes(raw[offset:offset + 4], 'big')
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(raw) or zlib.crc32(raw[offset + 4:end - 4]) != int.from_bytes(raw[end - 4:end], 'big'):
            raise ValueError('Original PNG chunk is truncated or corrupt')
        data = raw[offset + 8:end - 4]
        if header is None:
            if kind != b'IHDR' or length != 13:
                raise ValueError('Original PNG requires an initial IHDR')
            header = struct.unpack('>IIBBBBB', data)
            width, height, depth, color, compression, filtering, interlace = header
            if (not 1 <= width <= 10_000 or not 1 <= height <= 10_000
                    or width * height > IMAGE_MAX_PIXELS
                    or (width, height) != (image['width'], image['height'])
                    or (depth, color, compression, filtering, interlace) != (4, 0, 0, 0, 0)):
                raise ValueError('Original PNG IHDR differs from the supported image contract')
        elif kind == b'IDAT':
            if data_closed:
                raise ValueError('Original PNG IDAT chunks must be consecutive')
            compressed.extend(data)
        elif kind == b'IEND':
            if length or b'IDAT' not in seen or end != len(raw):
                raise ValueError('Invalid original PNG end or trailing bytes')
            ended = True
            break
        elif kind in {b'gAMA', b'bKGD', b'pHYs', b'tIME', b'tEXt'}:
            if kind != b'tEXt' and kind in seen:
                raise ValueError('Repeated original PNG ancillary chunk')
            if kind in {b'gAMA', b'bKGD', b'pHYs'} and b'IDAT' in seen:
                raise ValueError('Original PNG ancillary chunk appears after image data')
            valid = True
            if kind == b'gAMA': valid = length == 4 and int.from_bytes(data, 'big') > 0
            elif kind == b'bKGD': valid = length == 2 and int.from_bytes(data, 'big') <= 15
            elif kind == b'pHYs': valid = length == 9 and data[-1] in {0, 1}
            elif kind == b'tIME':
                valid = (length == 7 and int.from_bytes(data[:2], 'big') > 0
                         and 1 <= data[2] <= 12 and 1 <= data[3] <= 31
                         and data[4] < 24 and data[5] < 60 and data[6] <= 60)
                if valid:
                    try:
                        datetime(int.from_bytes(data[:2], 'big'), data[2], data[3])
                    except ValueError:
                        valid = False
            elif kind == b'tEXt':
                keyword, separator, value = data.partition(b'\0')
                valid = (bool(separator) and 1 <= len(keyword) <= 79 and b'\0' not in value
                         and not keyword.startswith(b' ') and not keyword.endswith(b' ') and b'  ' not in keyword
                         and all(32 <= c <= 126 or 161 <= c <= 255 for c in keyword))
            if not valid:
                raise ValueError('Malformed original PNG ancillary chunk')
        else:
            raise ValueError('Unsupported or repeated original PNG chunk')
        if kind != b'IDAT' and b'IDAT' in seen:
            data_closed = True
        seen.add(kind)
        offset = end
    if not ended or header is None:
        raise ValueError('Original PNG lacks complete image data and IEND')
    stride = 1 + (header[0] + 1) // 2
    expected = stride * header[1]
    try:
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(compressed, expected + 1)
    except zlib.error as error:
        raise ValueError('Invalid original PNG compressed image data') from error
    if (len(decoded) != expected or not inflater.eof or inflater.unconsumed_tail or inflater.unused_data
            or any(decoded[start] > 4 for start in range(0, expected, stride))):
        raise ValueError('Original PNG scanlines or compressed stream violate the bounded contract')


class _ImageHTML(HTMLParser):
    """Read full HTML context; selected lines cannot turn inert text into an img.

    This is a conservative source-link reader, not a browser or HTML executor.
    Raw-text elements and nonactive templates never contribute image identity.
    """
    CDATA_CONTENT_ELEMENTS = ('script', 'style', 'textarea', 'title', 'xmp', 'iframe',
                              'noembed', 'noframes', 'noscript', 'plaintext')
    INACTIVE = {'template', 'svg', 'math'}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.images, self.inactive = [], []
        self.plaintext = False
        self.lf_starts = [0] + [m.end() for m in re.finditer('\n', text)]
        self.line_starts = [0]
        for line in text.splitlines(keepends=True):
            self.line_starts.append(self.line_starts[-1] + len(line))
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == 'plaintext':
            self.plaintext = True
        if tag in self.INACTIVE:
            self.inactive.append(tag)
        if self.plaintext or self.inactive or tag != 'img':
            if tag == 'base' and not self.plaintext and not self.inactive:
                raise ValueError('Image identity does not support an HTML base override')
            return
        values = dict(attrs)
        if len(values) != len(attrs):
            raise ValueError('Duplicate attributes in HTML image tag')
        line, column = self.getpos()
        start = self.lf_starts[line - 1] + column
        end = start + len(self.get_starttag_text()) - 1
        self.images.append((bisect_right(self.line_starts, start),
                            bisect_right(self.line_starts, end), values))

    def handle_startendtag(self, tag, attrs):
        if tag in self.CDATA_CONTENT_ELEMENTS or tag in self.INACTIVE:
            raise ValueError('Ambiguous self-closing nonactive HTML context')
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.INACTIVE and self.inactive:
            # Do not recover malformed nesting by activating formerly inert text.
            if self.inactive[-1] != tag:
                raise ValueError('Ambiguous nonactive HTML context nesting')
            self.inactive.pop()


def _image_html(raw):
    if len(raw) > IMAGE_MAX_BYTES:
        raise ValueError('Original image identity HTML exceeds its byte limit')
    try:
        text = raw.decode('utf-8-sig')
        return text.splitlines(), _ImageHTML(text).images
    except (UnicodeError, AssertionError) as error:
        raise ValueError('Invalid UTF-8 HTML image identity source') from error


def _verify_image_identity(source, parent, parsed):
    link = source['original_image']['identity_link']
    lines, images = parsed
    first, last = link['first_line'], link['last_line']
    if last > len(lines) or digest('\n'.join(lines[first - 1:last]).encode()) != link['sha256']:
        raise ValueError('Image identity HTML line pin mismatch')
    matches = [attrs for start, end, attrs in images if first <= start <= end <= last
               and isinstance(attrs.get('src'), str)
               and not any(ord(c) <= 32 for c in attrs['src'])
               and urljoin(parent['url'], attrs['src']) == link['url']]
    if (len(matches) != 1
            or any(matches[0].get(key) != value for key, value in link['attributes'].items())):
        raise ValueError('Image identity needs one real complete HTML img with matching attributes')


def _archive_members(value):
    """Validate the ordered member contract even in a clone without raw files."""
    if not isinstance(value, list) or not value or len(value) > 1000:
        raise ValueError('Archive extraction requires an ordered member list')
    names = set()
    for member in value:
        if not isinstance(member, dict):
            raise ValueError('Invalid archive member pin')
        name = member.get('member')
        if (not _relative(name) or '\x00' in name or '\n' in name or '\r' in name
                or name in names
                or not isinstance(member.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', member['sha256'])
                or type(member.get('bytes')) is not int
                or not 0 <= member['bytes'] <= 32 * 1024 * 1024):
            raise ValueError('Invalid or repeated archive member pin')
        names.add(name)
    if sum(m['bytes'] for m in value) > 128 * 1024 * 1024:
        raise ValueError('Archive text selection exceeds its size limit')
    return value


def _archive_text(raw, members):
    """Read exact regular-file members in memory, never extract or execute them.

    The transport pin remains the real tar.gz response. Ordered member pins bind
    its contents; generated header lines identify their offsets in field spans.
    Member hashes use original bytes, including CRLF, before UTF-8 decoding.
    """
    members = _archive_members(members)
    wanted = {m['member']: m for m in members}
    found = {}
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode='r:gz') as archive:
            for entry in archive:
                if entry.name not in wanted:
                    continue
                member = wanted[entry.name]
                if entry.name in found or not entry.isfile() or entry.issparse():
                    raise ValueError('Archive member must be a unique regular file')
                if entry.size != member['bytes']:
                    raise ValueError('Archive member byte length mismatch')
                with archive.extractfile(entry) as handle:
                    content = handle.read(member['bytes'] + 1)
                if len(content) != member['bytes'] or digest(content) != member['sha256']:
                    raise ValueError('Archive member byte pin mismatch')
                found[entry.name] = content.decode('utf-8')
    except (tarfile.TarError, OSError, EOFError, UnicodeError) as error:
        raise ValueError('Invalid pinned UTF-8 tar.gz source') from error
    if found.keys() != wanted.keys():
        raise ValueError('Pinned archive member is missing')
    return ''.join('@@ archive member ' + m['member'] + '\n' + found[m['member']]
                   + ('' if found[m['member']].endswith('\n') else '\n')
                   for m in members)


def _pdf_layout_bytes(raw, expected_version):
    """Rebuild a pinned text derivative from the original PDF, without a shell."""
    if not raw.startswith(b'%PDF-'):
        raise ValueError('PDF extraction requires original PDF bytes')
    try:
        version = subprocess.run(['pdftotext', '-v'], capture_output=True, check=True,
                                 timeout=30)
        lines = (version.stderr or version.stdout).decode('utf-8').splitlines()
        if not lines or lines[0] != expected_version:
            raise ValueError('PDF text extractor version differs from the retained derivative')
        result = subprocess.run(['pdftotext', *PDF_ARGUMENTS], input=raw,
                                capture_output=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Pinned PDF extraction requires the recorded pdftotext tool') from error
    if not result.stdout.strip():
        raise ValueError('PDF extraction returned no text; visual/OCR review is separate')
    return result.stdout


def source_text(raw, extraction, *, extractor_version=None, archive_members=None):
    """Decode explicitly declared representations; never evaluate source code."""
    if extraction == 'utf8':
        return raw.decode('utf-8-sig')
    if extraction == 'json.source':
        value = json.loads(raw)['source']
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Published source response has no source text')
        return value
    if extraction == PDF_EXTRACTION:
        if not extractor_version:
            raise ValueError('PDF extraction requires a pinned extractor version')
        return _pdf_layout_bytes(raw, extractor_version).decode('utf-8')
    if extraction == TAR_EXTRACTION:
        return _archive_text(raw, archive_members)
    raise ValueError('Unsupported source-text extraction')


def _pdf_derivative(source):
    """Check the public parent/derivative contract without requiring private files."""
    derived = source.get('derived_text')
    if (source['role'] == 'source_code' or not isinstance(derived, dict)
            or derived.get('parent_pdf_sha256') != source['sha256']
            or not isinstance(derived.get('sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', derived['sha256'])
            or type(derived.get('bytes')) is not int or derived['bytes'] <= 0):
        raise ValueError('Invalid PDF parent or derived-text identity')
    path = derived.get('snapshot_path')
    if (not _relative(path) or not path.startswith('datasets/raw/sources/')
            or path == source['snapshot_path']):
        raise ValueError('Unsafe PDF derived-text snapshot path')
    generator = derived.get('generator', {})
    if (not isinstance(generator, dict)
            or generator.get('name') != 'pdftotext' or generator.get('arguments') != PDF_ARGUMENTS
            or not isinstance(generator.get('version'), str)
            or not re.fullmatch(r'pdftotext version [0-9][0-9A-Za-z.+_-]*', generator['version'])):
        raise ValueError('PDF derivative requires an explicit supported generator')
    return derived


def _visual_snapshot(path):
    return (_relative(path) and path.startswith('datasets/raw/sources/')
            and not any(c in path for c in '\x00\r\n'))


def _pdf_visual_contract(source):
    """Physical pages are separate evidence, never substitute text line spans.

    Limits apply before tools run. A field can cite the same page as another
    field; repeated references within one field cannot add evidence.
    """
    visual = source.get('visual_pages')
    if (source['role'] not in {'author_document', 'published_definition'}
            or not isinstance(visual, dict)
            or set(visual) != {'page_count', 'inspector', 'generator', 'pages'}
            or type(visual.get('page_count')) is not int
            or not 1 <= visual['page_count'] <= 1024
            or source['bytes'] > PDF_VISUAL_MAX_BYTES
            or not _visual_snapshot(source['snapshot_path'])):
        raise ValueError('Invalid visual PDF source or physical page count')
    generator, inspector = visual['generator'], visual['inspector']
    if (not isinstance(generator, dict)
            or set(generator) != {'name', 'version', 'dpi', 'arguments'}
            or generator.get('name') != 'pdftoppm'
            or generator.get('arguments') != PDF_VISUAL_ARGUMENTS
            or type(generator.get('dpi')) is not int or not 50 <= generator['dpi'] <= 200
            or not isinstance(generator.get('version'), str)
            or not re.fullmatch(r'pdftoppm version [0-9][0-9A-Za-z.+_-]*', generator['version'])
            or not isinstance(inspector, dict) or set(inspector) != {'name', 'version'}
            or inspector.get('name') != 'pdfinfo' or not isinstance(inspector.get('version'), str)
            or not re.fullmatch(r'pdfinfo version [0-9][0-9A-Za-z.+_-]*', inspector['version'])):
        raise ValueError('Visual PDF requires fixed supported tools and rendering parameters')
    pages = visual['pages']
    if not isinstance(pages, list) or not 1 <= len(pages) <= 64:
        raise ValueError('Visual PDF requires a bounded nonempty page selection')
    seen, paths = set(), set()
    for page in pages:
        if (not isinstance(page, dict)
                or set(page) != {'physical_page', 'parent_pdf_sha256', 'sha256', 'bytes', 'snapshot_path'}
                or type(page.get('physical_page')) is not int
                or not 1 <= page['physical_page'] <= visual['page_count']
                or page['physical_page'] in seen
                or page.get('parent_pdf_sha256') != source['sha256']
                or not isinstance(page.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', page['sha256'])
                or type(page.get('bytes')) is not int or not 67 <= page['bytes'] <= PDF_VISUAL_MAX_BYTES
                or not _visual_snapshot(page.get('snapshot_path'))
                or not page['snapshot_path'].endswith('.png')
                or page['snapshot_path'] in paths or page['snapshot_path'] == source['snapshot_path']):
            raise ValueError('Invalid, unsafe or repeated visual PDF page pin')
        seen.add(page['physical_page'])
        paths.add(page['snapshot_path'])
    if sum(page['bytes'] for page in pages) > 128 * 1024 * 1024:
        raise ValueError('Visual PDF page selection exceeds its byte limit')
    return visual


def _png_dimensions(raw):
    """Check real PNG framing, checksums and bounded IHDR dimensions."""
    if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > PDF_VISUAL_MAX_BYTES:
        raise ValueError('Visual page is not a bounded PNG')
    offset, dimensions, has_data = 8, None, False
    while offset + 12 <= len(raw):
        length = int.from_bytes(raw[offset:offset + 4], 'big')
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(raw) or zlib.crc32(raw[offset + 4:end - 4]) != int.from_bytes(raw[end - 4:end], 'big'):
            raise ValueError('Visual PNG chunk is truncated or corrupt')
        if dimensions is None:
            if kind != b'IHDR' or length != 13:
                raise ValueError('Visual PNG needs an initial IHDR')
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                '>IIBBBBB', raw[offset + 8:end - 4])
            allowed_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if (not 1 <= width <= 10_000 or not 1 <= height <= 10_000
                    or width * height > PDF_VISUAL_MAX_PIXELS
                    or depth not in allowed_depths.get(color, set())
                    or compression != 0 or filtering != 0 or interlace not in {0, 1}):
                raise ValueError('Visual PNG dimensions or format exceed the supported contract')
            dimensions = width, height
        elif kind == b'IHDR':
            raise ValueError('Visual PNG repeats IHDR')
        if kind == b'IDAT':
            has_data = has_data or length > 0
        if kind == b'IEND':
            if length != 0 or end != len(raw) or not has_data:
                raise ValueError('Visual PNG has no image data or has trailing content')
            return dimensions
        offset = end
    raise ValueError('Visual PNG is incomplete')


def _verify_pdf_visual(root, raw, visual):
    """Re-render pinned physical pages with fixed argv, no OCR or source code."""
    if not raw.startswith(b'%PDF-') or len(raw) > PDF_VISUAL_MAX_BYTES:
        raise ValueError('Visual PDF requires bounded original PDF bytes')
    env = dict(os.environ, LC_ALL='C')
    options = dict(capture_output=True, check=True, timeout=30, env=env)
    try:
        for tool in (visual['inspector'], visual['generator']):
            version = subprocess.run([tool['name'], '-v'], **options)
            lines = (version.stderr or version.stdout).decode('utf-8').splitlines()
            if not lines or lines[0] != tool['version']:
                raise ValueError('Visual PDF tool version differs from its recorded version')
        # Inspect every selected physical page before rendering any of them.
        sizes, total_pixels = {}, 0
        for page in visual['pages']:
            number = page['physical_page']
            info = subprocess.run(['pdfinfo', '-f', str(number), '-l', str(number), '-box', '-'],
                                  input=raw, **options).stdout.decode('utf-8')
            count = re.findall(r'^Pages:\s+(\d+)\s*$', info, re.M)
            box = re.findall(rf'^Page\s+{number}\s+MediaBox:\s+([-\d.]+)\s+([-\d.]+)\s+'
                             r'([-\d.]+)\s+([-\d.]+)\s*$', info, re.M)
            rotation = re.findall(rf'^Page\s+{number}\s+rot:\s+(\d+)\s*$', info, re.M)
            if (count != [str(visual['page_count'])] or len(box) != 1
                    or len(rotation) != 1 or int(rotation[0]) not in {0, 90, 180, 270}):
                raise ValueError('Visual PDF physical page count or page geometry mismatch')
            x0, y0, x1, y1 = map(float, box[0])
            widths = x1 - x0, y1 - y0
            if not all(math.isfinite(value) and 0 < value <= 14_400 for value in widths):
                raise ValueError('Visual PDF page geometry exceeds rendering limits')
            # pdfinfo rounds points; allow two pixels of measurement rounding.
            width, height = (math.ceil(value * visual['generator']['dpi'] / 72) + 2 for value in widths)
            if int(rotation[0]) in {90, 270}:
                width, height = height, width
            total_pixels += width * height
            if max(width, height) > 10_000 or width * height > PDF_VISUAL_MAX_PIXELS or total_pixels > 256_000_000:
                raise ValueError('Visual PDF selected pages exceed rendering pixel limits')
            sizes[number] = width, height
        for page in visual['pages']:
            saved = _pin(root, page['snapshot_path'], page)
            dimensions = _png_dimensions(saved)
            number = page['physical_page']
            if any(actual > bound or actual < bound - 4 for actual, bound in zip(dimensions, sizes[number])):
                raise ValueError('Visual PNG dimensions differ from the physical PDF page')
            with TemporaryFile() as output:
                subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number),
                                '-r', str(visual['generator']['dpi']), *PDF_VISUAL_ARGUMENTS, '-'],
                               input=raw, stdout=output, stderr=subprocess.PIPE, check=True, timeout=60, env=env)
                if output.tell() > PDF_VISUAL_MAX_BYTES:
                    raise ValueError('Rendered visual PNG exceeds its byte limit')
                output.seek(0)
                rebuilt = output.read(PDF_VISUAL_MAX_BYTES + 1)
            _png_dimensions(rebuilt)
            if rebuilt != saved:
                raise ValueError('Visual PDF page does not reconstruct from its parent')
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise ValueError('Visual PDF verification requires the recorded pdfinfo and pdftoppm tools') from error


def record_schema(root):
    """Extend the frozen metadata contract only with document-review status.

    Earlier code-only collections retain their original schema bytes. This
    collection accepts reviewed provider definitions without claiming code review.
    """
    schema = json.loads(read_below(root, 'metadata/schema.json'))
    for group in ('strategy_fields', 'factor_fields'):
        for field in schema['properties'][group]['properties'].values():
            statuses = field['properties']['status']['enum']
            if 'SOURCE_DESCRIPTION_REVIEWED' not in statuses:
                statuses.insert(1, 'SOURCE_DESCRIPTION_REVIEWED')
    return encoded(schema)


def _baseline_review(root, review, baseline_commit):
    """Bind compared definitions to local metadata bytes, not review prose.

    Pins are flat {native_id, path, sha256, row_sha256?} objects. Multiple
    paths may represent one native ID, but every compared ID needs a pin.
    This verifies the retained comparison inputs, not semantic equivalence or
    whether an arbitrary Git commit actually contains those paths.
    """
    if not isinstance(review, dict) or review.get('baseline_commit') != baseline_commit:
        raise ValueError('Collection duplicate review baseline commit mismatch')
    ids, pins = review.get('compared_native_ids'), review.get('compared_rule_pins')
    if (not isinstance(ids, list) or not all(isinstance(i, str) and i.strip() for i in ids)
            or len(set(ids)) != len(ids) or not isinstance(pins, list)):
        raise ValueError('Invalid collection baseline comparison membership')
    scope, terms = review.get('scope'), review.get('search_terms')
    if not ((isinstance(scope, str) and scope.strip()) or
            (isinstance(terms, list) and terms and all(isinstance(t, str) and t.strip() for t in terms))):
        raise ValueError('Collection baseline review needs its search scope')
    pinned_ids, paths = set(), set()
    for pin in pins:
        if not isinstance(pin, dict) or not {'native_id', 'path', 'sha256'} <= pin.keys():
            raise ValueError('Invalid collection baseline pin')
        native_id, path, checksum = pin['native_id'], pin['path'], pin['sha256']
        if (not isinstance(native_id, str) or native_id not in ids
                or not _relative(path) or not path.startswith('metadata/') or not path.endswith('.json')
                or path in paths or not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum)):
            raise ValueError('Invalid or repeated collection baseline pin')
        raw = read_below(root, path)
        if digest(raw) != checksum:
            raise ValueError('Collection baseline metadata byte pin mismatch')
        record = json.loads(raw)
        schema = record.get('schema_version')
        if schema in {'quantgraph-catalog-source-record/v1', 'quantgraph-knowledge-metadata/v1'}:
            known_ids = {record['record_id'], record['native_source_id']}
        elif schema == 'quantgraph-factor-metadata/v1':
            known_ids = {record['record_id'], *record['native_source_ids'], *record['identity']['source_record_ids']}
        else:
            raise ValueError('Collection baseline pin is not a supported metadata record')
        if native_id not in known_ids:
            raise ValueError('Collection baseline native identity mismatch')
        row_hash = record.get('provenance', {}).get('row_sha256')
        if schema == 'quantgraph-catalog-source-record/v1':
            values = {key: value['value'] for key, value in record['reported_fields'].items()}
            actual_row = digest(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                           separators=(',', ':'), allow_nan=False).encode())
            if row_hash != actual_row or values['id'] != record['record_id']:
                raise ValueError('Collection baseline CSV row does not reconstruct')
        if schema == 'quantgraph-catalog-source-record/v1' or 'row_sha256' in pin:
            if (not isinstance(pin.get('row_sha256'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', pin['row_sha256']) or pin['row_sha256'] != row_hash):
                raise ValueError('Collection baseline CSV row pin mismatch')
        paths.add(path)
        pinned_ids.add(native_id)
    if pinned_ids != set(ids):
        raise ValueError('Collection baseline ID and pin membership mismatch')


def validate_collection(root, directory, *, verify_snapshots=False):
    """Return records and declared reviews after structural/evidence validation.

    This verifies review integrity, not whether an author's algorithm works or
    whether the reviewer's economic-equivalence judgment is mathematically true.
    """
    root, directory = Path(root), str(directory)
    if not _relative(directory):
        raise ValueError('Unsafe collection directory')
    base = root / directory
    manifest = json.loads(read_below(root, directory + '/manifest.json'))
    if manifest.get('schema_version') != FORMAT:
        raise ValueError('Unsupported collection manifest')
    if manifest['batch_id'] != Path(directory).name:
        raise ValueError('Collection batch identity mismatch')
    pins = manifest['files']
    if set(pins) != {'index.json', 'schema.json', 'source-lock.json', 'reviews.json', 'quality-contract.json'}:
        raise ValueError('Collection manifest must pin every control file')
    controls = {name: json.loads(_pin(base, name, pin)) for name, pin in pins.items()}
    # Only the explicit document-review status extension is accepted.
    if read_below(base, 'schema.json') != record_schema(root):
        raise ValueError('Collection record schema drift')
    records = validate(base)
    index = controls['index.json']
    contract = controls['quality-contract.json']
    if (contract['batch_id'] != manifest['batch_id'] or contract['execution_trials'] != 0
            or contract['economic_independence_claimed'] is not False):
        raise ValueError('Collection contract changed its research boundary')
    if not re.fullmatch(r'[0-9a-f]{40}', contract['baseline']['git_commit']):
        raise ValueError('Collection baseline must pin a repository commit')
    lock, reviews = controls['source-lock.json'], controls['reviews.json']
    if lock.get('schema_version') != SOURCE_FORMAT or reviews.get('schema_version') != REVIEW_FORMAT:
        raise ValueError('Unsupported collection evidence format')
    if lock['batch_id'] != manifest['batch_id'] or reviews['batch_id'] != manifest['batch_id']:
        raise ValueError('Collection control file identity mismatch')
    sources = {source['id']: source for source in lock['sources']}
    if len(sources) != len(lock['sources']):
        raise ValueError('Duplicate collection source ID')
    texts, visual_sources, visual_paths, image_sources = {}, {}, set(), {}
    # A visual derivative cannot reuse any original/derived-text path, even
    # under another source ID. Existing text collections keep their contracts.
    reserved_paths = {s['snapshot_path'] for s in sources.values()}
    reserved_paths.update(s['derived_text']['snapshot_path'] for s in sources.values()
                          if isinstance(s.get('derived_text'), dict) and 'snapshot_path' in s['derived_text'])
    for sid, source in sources.items():
        url = urlsplit(source['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Invalid collection source URL')
        if source['http_status'] != 200 or not re.fullmatch(r'[0-9a-f]{64}', source['sha256']):
            raise ValueError('Collection source must be a successful pinned fetch')
        if type(source['bytes']) is not int or source['bytes'] <= 0:
            raise ValueError('Invalid source byte length')
        if source['role'] not in CONTENT_ROLES | {'license', 'attribution', 'source_index'}:
            raise ValueError('Unsupported collection source role')
        _date(source['retrieved_at'])
        snapshot = source['snapshot_path']
        if not _relative(snapshot) or not snapshot.startswith('datasets/raw/sources/'):
            raise ValueError('Unsafe collection snapshot path')
        if source['revision_kind'] == 'git_commit':
            revision = source['revision']
            if (url.hostname != 'github.com' or not re.fullmatch(r'[0-9a-f]{40}', revision)
                    or f'/blob/{revision}/' not in unquote(url.path)):
                raise ValueError('Git source must pin the same full commit in its URL')
        elif source['revision_kind'] != 'content_snapshot' or not source['revision']:
            raise ValueError('Unsupported collection source revision')
        if source['extraction'] not in {'utf8', 'json.source', PDF_EXTRACTION, PDF_VISUAL_EXTRACTION,
                                        TAR_EXTRACTION, IMAGE_EXTRACTION}:
            raise ValueError('Unsupported source extraction')
        if source['extraction'] == TAR_EXTRACTION:
            _archive_members(source.get('archive_members'))
        elif 'archive_members' in source:
            raise ValueError('Archive member pins require archive extraction')
        derived = _pdf_derivative(source) if source['extraction'] == PDF_EXTRACTION else None
        if derived is None and 'derived_text' in source:
            raise ValueError('Derived text requires PDF extraction')
        visual = _pdf_visual_contract(source) if source['extraction'] == PDF_VISUAL_EXTRACTION else None
        if visual is None and 'visual_pages' in source:
            raise ValueError('Visual page pins require visual PDF extraction')
        if visual:
            paths = {page['snapshot_path'] for page in visual['pages']}
            if paths & (visual_paths | reserved_paths):
                raise ValueError('Visual PDF derivative snapshot paths must be unique')
            visual_paths.update(paths)
            visual_sources[sid] = {page['physical_page']: page for page in visual['pages']}
        if source['extraction'] == IMAGE_EXTRACTION:
            image_sources[sid] = _image_contract(source)
        elif 'original_image' in source:
            raise ValueError('Original image contract requires original image extraction')
    # Finish all public image bounds and provenance checks before inflating any
    # image. HTML source order in the lock does not affect its identity link.
    snapshot_counts = Counter(s['snapshot_path'] for s in sources.values())
    snapshot_counts.update(s['derived_text']['snapshot_path'] for s in sources.values()
                           if isinstance(s.get('derived_text'), dict) and 'snapshot_path' in s['derived_text'])
    if (len(image_sources) > 64 or sum(sources[sid]['bytes'] for sid in image_sources) > 128 * 1024 * 1024
            or sum(image['width'] * image['height'] for image in image_sources.values()) > 256_000_000):
        raise ValueError('Original image collection exceeds its resource limits')
    image_parents = set()
    for sid, image in image_sources.items():
        link = image['identity_link']
        parent = sources.get(link['source_id'])
        if (parent is None or parent['role'] not in {'attribution', 'source_index'}
                or parent['extraction'] != 'utf8' or parent['sha256'] != link['source_sha256']
                or parent['bytes'] > IMAGE_MAX_BYTES or not _visual_snapshot(parent['snapshot_path'])):
            raise ValueError('Original image requires a pinned HTML identity source')
        if snapshot_counts[sources[sid]['snapshot_path']] != 1 or sources[sid]['snapshot_path'] in visual_paths:
            raise ValueError('Original image snapshot paths must be unique')
        image_parents.add(link['source_id'])
    if verify_snapshots:
        parsed_html = {}
        for sid, source in sources.items():
            snapshot = source['snapshot_path']
            raw = _pin(root, snapshot, source)
            if sid in image_parents:
                parsed_html[sid] = _image_html(raw)
            if sid in image_sources:
                _verify_original_png(raw, image_sources[sid])
            elif sid in visual_sources:
                _verify_pdf_visual(root, raw, source['visual_pages'])
            elif source['extraction'] == PDF_EXTRACTION:
                derived = source['derived_text']
                saved = _pin(root, derived['snapshot_path'], derived)
                rebuilt = _pdf_layout_bytes(raw, derived['generator']['version'])
                if rebuilt != saved:
                    raise ValueError('PDF text derivative does not reconstruct from its parent')
                texts[sid] = saved.decode('utf-8').splitlines()
            else:
                texts[sid] = source_text(raw, source['extraction'],
                                         archive_members=source.get('archive_members')).splitlines()
        for sid, image in image_sources.items():
            parent_id = image['identity_link']['source_id']
            _verify_image_identity(sources[sid], sources[parent_id], parsed_html[parent_id])
    refs = {_identity(ref): ref for ref in index['records']}
    decisions = {_identity(review): review for review in reviews['records']}
    if len(decisions) != len(reviews['records']) or set(decisions) != set(refs):
        raise ValueError('Collection review membership mismatch')
    accepted, seen_definitions, used_sources = Counter(), set(), set()
    source_keys, source_owners = {}, {}
    for record in records:
        key, kind = _identity(record), record['entity_type']
        review, ref = decisions[key], refs[key]
        if review['record_sha256'] != ref['sha256']:
            raise ValueError('Collection review targets another metadata version')
        _date(review['reviewed_at'])
        if not review['reviewer'] or review['method'] != 'PER_RECORD_SOURCE_REVIEW':
            raise ValueError('Collection needs an attributable per-record review')
        declared = {source['id']: source for source in record['sources']}
        if len(declared) != len(record['sources']) or not set(declared) <= set(sources):
            raise ValueError('Collection record source membership mismatch')
        used_sources.update(declared)
        for sid, source in declared.items():
            if any(source[field] != sources[sid][field] for field in ('url', 'revision', 'sha256')):
                raise ValueError('Collection source reference differs from its lock')
            if sid in image_sources and image_sources[sid]['identity_link']['source_id'] not in declared:
                raise ValueError('Record image source must declare its HTML identity source')
        if (record['lab'] is not None or record['rights']['source_fulltext_included'] is not False
                or record['rights']['raw_data_included'] is not False):
            raise ValueError('Collection cannot include source fulltext, data or Lab results')
        if review['states'] != dict(computation_semantics='NOT_EXECUTED', economic_validity='NOT_TESTED',
                                    commercial_use='REVIEW_REQUIRED'):
            raise ValueError('Collection review cannot promote execution or economic status')
        fields = record.get('strategy_fields') or record['factor_fields']
        spans = review['field_spans']
        field_pages = review.get('field_pages', {})
        field_images = review.get('field_images', {})
        if (not isinstance(spans, dict) or not isinstance(field_pages, dict) or not isinstance(field_images, dict)
                or not set(spans) <= set(fields) or not set(field_pages) <= set(fields)
                or not set(field_images) <= set(fields)):
            raise ValueError('Review references an unknown metadata field')
        for field in fields.values():
            if (set(field['evidence']) & (set(visual_sources) | set(image_sources))
                    and field['status'] == 'SOURCE_CODE_REVIEWED'):
                raise ValueError('Visual PDF or original image evidence cannot establish a code-reviewed field')
        for field_name, locations in spans.items():
            for location in locations:
                sid = location['source_id']
                start, end = location['first_line'], location['last_line']
                if sid not in declared or sid not in fields[field_name]['evidence']:
                    raise ValueError('Review span is not field evidence')
                if sid in visual_sources or sid in image_sources:
                    raise ValueError('Visual PDF pages cannot masquerade as text line spans')
                if sources[sid]['role'] not in CONTENT_ROLES:
                    raise ValueError('License or directory cannot establish a definition')
                if (fields[field_name]['status'] == 'SOURCE_CODE_REVIEWED'
                        and sources[sid]['role'] != 'source_code'):
                    raise ValueError('Code-reviewed field requires source-code evidence')
                if (type(start) is not int or type(end) is not int or not 1 <= start <= end
                        or not re.fullmatch(r'[0-9a-f]{64}', location['sha256'])):
                    raise ValueError('Invalid source line span')
                if verify_snapshots:
                    lines = texts[sid]
                    if end > len(lines) or digest('\n'.join(lines[start - 1:end]).encode()) != location['sha256']:
                        raise ValueError('Source span does not match saved bytes')
        for field_name, locations in field_pages.items():
            if not isinstance(locations, list) or not locations:
                raise ValueError('Visual field evidence needs a nonempty page-reference list')
            seen_pages = set()
            for location in locations:
                if (not isinstance(location, dict)
                        or set(location) != {'source_id', 'physical_page', 'sha256'}
                        or not isinstance(location.get('source_id'), str)
                        or type(location.get('physical_page')) is not int):
                    raise ValueError('Invalid visual field page reference')
                sid, number = location['source_id'], location['physical_page']
                page = visual_sources.get(sid, {}).get(number)
                if (sid not in declared or sid not in fields[field_name]['evidence'] or page is None
                        or fields[field_name]['status'] != 'SOURCE_DESCRIPTION_REVIEWED'
                        or location['sha256'] != page['sha256']):
                    raise ValueError('Visual page is not declared description-reviewed field evidence')
                identity = page['parent_pdf_sha256'], number
                if identity in seen_pages:
                    raise ValueError('Repeated visual page reference in a field')
                seen_pages.add(identity)
        for field_name, locations in field_images.items():
            if not isinstance(locations, list) or not locations:
                raise ValueError('Original image field evidence requires a nonempty reference list')
            seen_images = set()
            for location in locations:
                if (not isinstance(location, dict)
                        or set(location) != {'source_id', 'sha256', 'printed_page'}
                        or not isinstance(location.get('source_id'), str)):
                    raise ValueError('Invalid original image field reference')
                sid = location['source_id']
                image = image_sources.get(sid)
                if (sid not in declared or sid not in fields[field_name]['evidence'] or image is None
                        or fields[field_name]['status'] != 'SOURCE_DESCRIPTION_REVIEWED'
                        or location['sha256'] != sources[sid]['sha256']
                        or location['printed_page'] != image['printed_page']):
                    raise ValueError('Original image is not declared description-reviewed field evidence')
                if location['sha256'] in seen_images:
                    raise ValueError('Repeated original image reference in a field')
                seen_images.add(location['sha256'])
        outcome = review['dedup']['outcome']
        if outcome not in NO_CREDIT | {'REVIEWED_DISTINCT_CONSTRUCTION'}:
            raise ValueError('Unknown collection duplicate decision')
        if not review['dedup']['reason'] or not review['dedup']['baseline_review']:
            raise ValueError('Collection needs baseline duplicate-review evidence')
        _baseline_review(root, review['dedup']['baseline_review'], contract['baseline']['git_commit'])
        if review['dedup']['unresolved_candidates']:
            if outcome == 'REVIEWED_DISTINCT_CONSTRUCTION':
                raise ValueError('Unresolved similar definitions cannot count as new')
        if outcome == 'REVIEWED_DISTINCT_CONSTRUCTION':
            if review['core_rules_complete'] is not True:
                raise ValueError('Incomplete definition cannot count toward target')
            for field_name in CORE[kind]:
                if fields[field_name]['status'] not in {'SOURCE_CODE_REVIEWED', 'SOURCE_DESCRIPTION_REVIEWED'}:
                    raise ValueError('Core rule is not source reviewed')
                if not spans.get(field_name) and not field_pages.get(field_name) and not field_images.get(field_name):
                    raise ValueError('Core rule needs precise source evidence')
            if (not isinstance(review['definition_signature'], str) or not review['definition_signature'].strip()
                    or review['definition_signature'] in seen_definitions):
                raise ValueError('Repeated definition cannot increase collection quota')
            keys = collection_source_keys(record, review, sources)
            for source_key in sorted(keys):
                if source_key in source_owners:
                    raise ValueError(f'Repeated collection source definition: {key} and '
                                     f'{source_owners[source_key]} share {source_key}')
            source_owners.update((source_key, key) for source_key in keys)
            source_keys[key] = keys
            seen_definitions.add(review['definition_signature'])
            accepted[kind] += 1
    if used_sources != set(sources):
        raise ValueError('Unreferenced source in collection lock')
    counts = dict(records=len(records), strategy=accepted['strategy'], factor=accepted['factor'], execution_trials=0)
    if manifest['counts'] != counts:
        raise ValueError('Collection counts differ from reviewed definitions')
    return dict(records=records, reviews=decisions, manifest=manifest, counts=counts, source_keys=source_keys,
                raw_evidence_verified=bool(verify_snapshots))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--verify-snapshots', action='store_true')
    args = parser.parse_args()
    result = validate_collection(args.root, args.directory, verify_snapshots=args.verify_snapshots)
    print(json.dumps(dict(status='PASS', **result['counts'], raw_evidence_verified=result['raw_evidence_verified'])))


if __name__ == '__main__':
    main()
