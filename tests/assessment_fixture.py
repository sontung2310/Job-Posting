from pathlib import Path
import os
import shutil


def write_pdf(path, text):
    content = f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream']
    result, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result)); result.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(result)
    result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    path.write_bytes(result)


def fixture(root):
    vault, resumes = root/'vault', root/'resumes'
    (vault/'01 Profile').mkdir(parents=True); (vault/'05 Evidence').mkdir(); resumes.mkdir()
    metadata = 'status: verified\nsource:\n  - "user-confirmed: fixture"\nlast_verified: 2026-10-01\n'
    (vault/'01 Profile/Work Authorization.md').write_text('---\ntype: constraint\n'+metadata+'''visa_type: fixture
work_rights_regions: Australia
full_current_work_rights: Australia
sponsorship_required: false
permanent_resident: false
australian_citizen: false
new_zealand_citizen: false
---
## Rights
Verified rights
''')
    (vault/'01 Profile/Career Profile.md').write_text('---\ntype: profile\n'+metadata+'education:\n  - Master of Science\n---\n## Education\nMaster of Science\n')
    (vault/'05 Evidence/Python.md').write_text('---\ntype: evidence\n'+metadata+'skills:\n  - Python\n---\n## Claim\nBuilt Python services.\n')
    (vault/'01 Profile/Target Roles.md').write_text('---\ntype: preferences\n'+metadata+'---\nPython roles\n')
    for name, text in [('ai.pdf', 'Built Python services.'), ('cv.pdf', 'Computer vision research.')]:
        write_pdf(resumes/name, text)
    return vault, resumes
