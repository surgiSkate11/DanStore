import glob, re

files = glob.glob('templates/sorteos/*.html')

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        c = file.read()
        
    m_back = re.search(r'([ \t]*<a href="\{% url \'detalle_sorteo\' sorteo\.id %\}\" class=\"back-link\">.*?</a\s*>)', c, re.DOTALL)
    m_target = re.search(r'([ \t]*<div class="participants-list" id="partList"></div>\s*</div\s*>)', c, re.DOTALL)
    
    if m_back and m_target:
        # if back occurs after target we already moved it
        if m_back.start() > m_target.start(): continue
        
        back_str = m_back.group(1)
        # remove it
        c = c.replace(back_str, '')
        
        target_str = m_target.group(1)
        # re-insert below
        c = c.replace(target_str, target_str + '\n\n' + back_str)
        
        with open(f, 'w', encoding='utf-8') as handle:
            handle.write(c)
