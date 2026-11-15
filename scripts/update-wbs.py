"""Preserve the XLSX package and original owners/progress; patch verified cells only.

Uses ZIP/XML, retaining drawings, formats and unrelated workbook parts. Formulas
get recalculated by Excel; the corrected summary caches are also written here.
"""
import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def cells(xml, shared):
    result = {}
    for cell in ET.fromstring(xml).findall('.//s:sheetData/s:row/s:c', NS):
        val = cell.find('s:v', NS)
        text = val.text if val is not None else ''.join(cell.find('s:is', NS).itertext()) if cell.find('s:is', NS) is not None else ''
        if cell.get('t') == 's' and text:
            text = shared[int(text)]
        result[cell.get('r')] = text
    return result


def put(xml, ref, value, *, formula=None, cache=None):
    pattern = rf'<c\b(?=[^>]*\br="{re.escape(ref)}")[^>]*?(?:/>|>.*?</c>)'
    old = re.search(pattern, xml, re.S)
    style = re.search(r'\bs="([^"]+)"', old.group(0)) if old else None
    attrs = f'r="{ref}"' + (f' s="{style.group(1)}"' if style else '')
    if formula is not None:
        cached = '' if cache is None else escape(str(cache))
        if isinstance(cache, str):
            attrs += ' t="str"'
        body = f'<c {attrs}><f>{escape(formula)}</f><v>{cached}</v></c>'
    elif isinstance(value, (int, float)):
        body = f'<c {attrs}><v>{value}</v></c>'
    else:
        body = f'<c {attrs} t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'
    if old:
        return xml[:old.start()] + body + xml[old.end():]
    row = re.search(r'\d+', ref).group()
    row_pattern = rf'(<row\b(?=[^>]*\br="{row}")[^>]*>)(.*?)(</row>)'
    match = re.search(row_pattern, xml, re.S)
    if not match:
        raise ValueError(f'Missing original row {row}; refusing structural guess')
    def column(cell_ref):
        number = 0
        for letter in re.match('[A-Z]+', cell_ref).group():
            number = number * 26 + ord(letter) - 64
        return number
    position = match.end(2)
    for cell in re.finditer(r'<c\b[^>]*\br="([A-Z]+\d+)"', match.group(2)):
        if column(cell.group(1)) > column(ref):
            position = match.start(2) + cell.start()
            break
    return xml[:position] + body + xml[position:]


def update(original, entries, output, audit_path):
    if output.exists() or original.resolve() == output.resolve():
        raise ValueError('Use a fresh output; the original is immutable')
    with zipfile.ZipFile(original) as z:
        blobs = {n: z.read(n) for n in z.namelist()}
    shared = [''.join(node.itertext()) for node in ET.fromstring(blobs['xl/sharedStrings.xml']).findall('s:si', NS)]
    wbs = blobs['xl/worksheets/sheet2.xml'].decode()
    roles = blobs['xl/worksheets/sheet1.xml'].decode()
    history = blobs['xl/worksheets/sheet4.xml'].decode()
    old = cells(wbs, shared)
    role_cells = cells(roles, shared)
    tasks = {old[f'A{r}']: r for r in range(17, 57)}
    if len(tasks) != 40 or set(tasks) != {item['id'] for item in entries} or len(entries) != 40:
        raise ValueError('All original 40 task IDs must occur exactly once')
    headers = {'Q': '구현 파일', 'R': '실제 시험 결과', 'S': '원본 증적', 'T': '남은 작업',
               'U': '검증 상태·판단 근거', 'V': '역할표와 비교', 'W': '일정 검토'}
    for col, label in headers.items():
        wbs = put(wbs, col+'4', label)
    audit = []
    today = datetime(2026, 11, 16)
    for item in entries:
        row = tasks[item['id']]
        owner, progress = old[f'D{row}'], old[f'I{row}']
        role = next((role_cells[f'B{r}'] for r in range(5, 9) if role_cells[f'A{r}'] == owner), '-')
        role_note = '표기 일치' if old.get(f'E{row}') == role or owner == '팀 전체' else f'표기/업무영역 확인 필요: 역할표={role}; 원본 담당 {owner} 유지'
        if item.get('role_review'):
            role_note += '; ' + item['role_review']
        due = datetime(1899, 12, 30) + timedelta(days=float(old[f'G{row}']))
        schedule = ('기한 경과·완료 근거 재검토; 새 일정 미승인' if due < today and float(progress) < 1 else '원래 일정 유지; AWS 검증 일정은 승인 후 확정')
        values = {'Q': '\n'.join(item['files']), 'R': item['tests'], 'S': '\n'.join(item['evidence']),
                  'T': item['remaining'], 'U': item['status']+' / '+item['basis'], 'V': role_note, 'W': schedule}
        for col, value in values.items():
            wbs = put(wbs, f'{col}{row}', value)
        state = '완료' if old[f'J{row}'] == '완료' else item['status']
        wbs = put(wbs, f'J{row}', state)
        wbs = put(wbs, f'M{row}', old.get(f'M{row}', '')+'\n2026-11-16: 검증 근거 Q:W 참조. 원본 진행률 유지.')
        audit.append({'id': item['id'], 'owner_unchanged': owner, 'progress_unchanged': progress,
                      'previous_status': old[f'J{row}'], 'status': state, 'basis': item['basis'],
                      'due': due.date().isoformat(), 'schedule': schedule, 'role_review': role_note})
    wbs = put(wbs, 'P4', None, formula='COUNTA(C17:C56)', cache=40)
    wbs = put(wbs, 'P5', None, formula='COUNTIF(J17:J56,"완료")', cache=sum(t['status']=='완료' for t in audit))
    mean = sum(float(old[f'I{r}']) for r in range(17,57))/40
    wbs = put(wbs, 'P6', None, formula='IFERROR(AVERAGE(I17:I56),0)', cache=mean)
    wbs = put(wbs, 'E27', None, formula="IFERROR(VLOOKUP(D27,'팀원별 역할'!$A$5:$B$8,2,0),\"\")", cache=role_cells['B5'])
    means=[]
    for row in range(5, 9):
        owner=role_cells[f'A{row}']
        values=[float(old[f'I{r}']) for r in range(17,57) if old[f'D{r}']==owner]
        average=sum(values)/len(values)
        means.append(average)
        roles=put(roles, f'D{row}', None, formula=f'COUNTIF(WBS!$D$17:$D$56,A{row})', cache=len(values))
        roles=put(roles, f'E{row}', None, formula=f'IFERROR(AVERAGEIF(WBS!$D$17:$D$56,A{row},WBS!$I$17:$I$56),0)', cache=average)
        roles=put(roles, f'F{row}', '원본 담당 유지. WBS V열의 표기·업무영역 차이는 팀 검토 필요.')
    roles=put(roles, 'B11', None, formula='AVERAGE(E5:E8)', cache=sum(means)/4)
    # Fix existing truncated shared formula anchors without changing original records.
    history=history.replace('$A$5:$M$38', '$A$17:$M$56').replace('$L$5:$L$38', '$L$17:$L$56')
    history=put(history, 'D32', None, formula='COUNTIF(B5:B29,"?*")+COUNT(B5:B29)', cache=2)
    for col, val in {'B':'최종 통합 전체', 'C':'40개 작업 증적 연결·수식 수정·AWS 승인 분리', 'D':'팀 전체',
                     'J':'범위·검증 상태 재평가', 'L':(today-datetime(1899,12,30)).days, 'M':'검토중',
                     'N':'일정/진행률/담당은 원본 유지. WBS W열의 기한 경과 항목은 새 일정 합의 필요. 1초 RTO는 미달성/미검증 그대로 유지.'}.items():
        history=put(history, col+'6', val)
    # Extend editable area, preserving original styling/drawings rather than re-saving with a new engine.
    wbs=re.sub(r'<dimension ref="[^"]+"\s*/>', '<dimension ref="A1:W56"/>', wbs)
    # Give the evidence columns room without reformatting the original workbook.
    wbs=wbs.replace('</cols>', '<col min="17" max="23" width="48" customWidth="1"/></cols>')
    wbs=wbs.replace('$A$6:$A$7', '$A$5:$A$8')
    styles = blobs['xl/styles.xml'].decode()
    xfs = re.search(r'<cellXfs\b[^>]*count="(\d+)"[^>]*>(.*?)</cellXfs>', styles, re.S)
    style_id = int(xfs.group(1))
    wrap = '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
    new_xfs = xfs.group(0).replace(f'count="{style_id}"', f'count="{style_id+1}"', 1).replace('</cellXfs>', wrap+'</cellXfs>')
    blobs['xl/styles.xml'] = (styles[:xfs.start()]+new_xfs+styles[xfs.end():]).encode()
    wbs = re.sub(r'<c r="([Q-W]\d+)"([^>]*)>',
                 lambda m: f'<c r="{m.group(1)}" s="{style_id}"'+re.sub(r'\s+s="[^"]*"','',m.group(2))+'>', wbs)
    blobs['xl/worksheets/sheet1.xml']=roles.encode()
    blobs['xl/worksheets/sheet2.xml']=wbs.encode()
    blobs['xl/worksheets/sheet4.xml']=history.encode()
    workbook=blobs['xl/workbook.xml'].decode()
    workbook=workbook.replace('$A$6:$A$7', '$A$5:$A$8')
    workbook=re.sub(r'<calcPr\b[^>]*/>', '<calcPr calcId="191029" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>', workbook)
    blobs['xl/workbook.xml']=workbook.encode()
    if 'xl/calcChain.xml' in blobs:
        del blobs['xl/calcChain.xml']
        for name in ['xl/_rels/workbook.xml.rels','[Content_Types].xml']:
            text=blobs[name].decode()
            text=re.sub(r'<(?:Relationship|Override)\b[^>]*calcChain[^>]*/>', '', text)
            blobs[name]=text.encode()
    # Validate before publishing a workbook; never leave an invalid deliverable.
    for name, blob in blobs.items():
        if name.endswith('.xml'):
            ET.fromstring(blob)
    after=cells(wbs, shared)
    assert all(after[f'{c}{r}']==old[f'{c}{r}'] for c in ['A','C','D','F','G','I'] for r in range(17,57))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, blob in blobs.items():
            z.writestr(name, blob)
    audit_path.write_text(json.dumps({'source_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
        'task_count':40,'original_progress_mean':mean,'numeric_progress_changed':False,'tasks':audit},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original',type=Path,required=True)
    p.add_argument('--mapping',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    a=p.parse_args()
    update(a.original,json.loads(a.mapping.read_text(encoding='utf-8'))['tasks'],a.output,a.audit)
    print('Updated all 40 tasks; original owners, dates, names, numeric progress preserved.')
