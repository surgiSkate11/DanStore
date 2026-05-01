import glob, re

files = glob.glob('templates/sorteos/*.html')
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        c = file.read()
        
    # 1. Config inputs (Duracion, vueltas extras) -> reducir tamano
    c = re.sub(
        r'\.config-group input\s*\{([^\}]*?)width:\s*70px;([^\}]*?)padding:\s*2px\s*4px;([^\}]*?)\}',
        r'.config-group input {\1width: 55px;\2padding: 1px 4px;\3 font-size: 0.85rem;}',
        c
    )
    # also for single line representations:
    c = re.sub(
        r'(\.config-group input\s*\{[^}]*)width:\s*70px;([^}]*)padding:\s*2px\s*4px;([^}]*\})',
        r'\1width: 55px;\2padding: 1px 4px; font-size: 0.85rem;\3',
        c
    )
    
    # 2. Reduce config panel overall padding/gap slightly to make it fit better if not done already
    c = re.sub(r'(\.config-wrapper\s*\{[^}]*)padding:\s*10px\s*12px;([^}]*)gap:\s*8px;([^}]*\})',
               r'\1padding: 8px 10px;\2gap: 6px;\3', c)
    c = re.sub(r'(\.config-group label\s*\{[^}]*)font-size:\s*0\.8rem;([^}]*\})',
               r'\1font-size: 0.75rem;\2', c)

    # 3. Center "Proximo premio" (only present in ruleta originally, but let's be thorough if others have it)
    # .premio-box and .premio-box .label and .premio-box .name
    if '.premio-box {' in c:
        c = re.sub(r'(\.premio-box\s*\{[^}]*)border-left:\s*5px\s*solid\s*#3b82f6;([^}]*\})', 
                   r'\1text-align: center;\2', c)
        c = re.sub(r'(\.premio-box\s*\.name\s*\{[^}]*)display:\s*flex;([^}]*\})',
                   r'\1display: flex; justify-content: center;\2', c)
                   
    # 4. Increase participants & prize icons
    # Prize icon inside .premio-box .name i
    c = re.sub(r'(\.premio-box\s*\.name\s*i\s*\{[^}]*)font-size:\s*1\.25rem;([^}]*\})',
               r'\1font-size: 1.5rem; margin-right: 4px;\2', c)
               
    # Stat-card icons
    c = re.sub(r'(\.stat-card\s*i\s*\{[^}]*)font-size:\s*1rem;([^}]*\})',
               r'\1font-size: 1.25rem;\2', c)

    # Participant icons in the list (injected via JS usually)
    c = re.sub(r'(class=[\'\"]bi bi-person-fill[\'\"][^>]*font-size:\s*)0\.95rem;([^\'\"]*)',
               r'\g<1>1.2rem;\2', c)
               
    c = re.sub(r'(class=[\'\"]bi bi-person-fill[\'\"][^>]*font-size:\s*)1rem;([^\'\"]*)',
               r'\g<1>1.2rem;\2', c)

    with open(f, 'w', encoding='utf-8') as file:
        file.write(c)

print("Ajustes realizados!")
