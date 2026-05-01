import glob, re

for f in glob.glob('templates/sorteos/*.html'):
    with open(f, 'r', encoding='utf-8') as handle:
        c = handle.read()
    m_back = re.search(r'\n*[ \t]*<a href="\{% url \'detalle_sorteo\' sorteo\.id %\}.*?</a\>\s*', c, re.DOTALL)
    m_target = re.search(r'<div class="participants-list" id="partList">.*?</div>\s*</div>', c, re.DOTALL)
    if m_back and m_target:
        print('Found both in', f)
        b_str = m_back.group(0)
        t_str = m_target.group(0)
        if c.find(b_str) < c.find(t_str):
            c = c.replace(b_str, '')
            # append b_str after t_str
            c = c.replace(t_str, t_str + b_str)
            with open(f, 'w', encoding='utf-8') as h:
                h.write(c)
            print('Moved in', f)
