"""Expose bounded JUnit failures as Actions annotations when artifact egress is blocked."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def annotations(path):
    tree=ET.parse(path)
    result=[]
    for case in tree.iter('testcase'):
        for failure in list(case):
            if failure.tag not in ('failure','error'):continue
            title=(case.get('classname','')+'.'+case.get('name',''))[:250]
            text=(failure.text or failure.get('message','No traceback'))[-5000:]
            escape=lambda value:value.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            result.append('::error title='+escape(title).replace(',','%2C').replace(':','%3A')+'::'+escape(text))
            if len(result)>=10:return result
    return result


if __name__=='__main__':
    for filename in sys.argv[1:]:
        try:
            for message in annotations(Path(filename)):print(message)
        except (OSError,ET.ParseError) as exc:
            print('::warning::JUnit diagnostic report unavailable: '+str(exc).replace('\n',' '))
