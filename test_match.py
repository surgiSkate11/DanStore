import re
with open('templates/sorteos/ruleta.html', 'r', encoding='utf-8') as file:
    c = file.read()
m_back = re.search(r'<a href="\{% url \'detalle_sorteo\' sorteo\.id %\}\" class=\"back-link\">.*?</a\s*>', c, re.DOTALL)
m_target = re.search(r'<div class=\"participants-list\" id=\"partList\"></div>\s*</div\s*>', c, re.DOTALL)
print(m_back is not None)
print(m_target is not None)
