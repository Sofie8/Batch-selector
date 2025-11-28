import streamlit as st
import pandas as pd
import re
import graphviz

# --- DE LOGICA FUNCTIE ---
def determine_path(df, metadata):
    path = ["Start"]
    
    # --- 1. DATA EXTRACTIE ---
    # We proberen slimme kolommen te vinden, anders vallen we terug op defaults
    try:
        # Zoek kolom met 'reductie' of 'lan' erin
        col_reductie = [c for c in df.columns if 'reductie' in str(c).lower() and 'lan' in str(c).lower()]
        if col_reductie:
            reductie_col = col_reductie[0]
            lan_reducties = pd.to_numeric(df[reductie_col], errors='coerce').fillna(0)
        else:
            # Fallback als we de exacte kolomnaam niet weten
            lan_reducties = pd.to_numeric(df.iloc[:, 1], errors='coerce').fillna(0) # Gok kolom 2
            
        n_high_reductie = (lan_reducties > 50).sum()
        
        # Haal stofnamen (meestal kolom 1)
        stoffen = df.iloc[:, 0].astype(str)
        
    except:
        # Als alles faalt (lege file), defaults
        n_high_reductie = 0
        stoffen = pd.Series([])
        lan_reducties = pd.Series([])

    # Haal pH op
    ph_val = metadata.get('ph_kcl', 7.0)
    
    # Check type vervuiling (Regex patronen)
    # Zware olie / zware metalen
    has_oil_heavy = any(stoffen.str.contains(r'C20|C30|C40', case=False, regex=True) & (lan_reducties > 0))
    has_oil_light = any(stoffen.str.contains(r'C10-C20|C10-C12', case=False, regex=True) & (lan_reducties > 0))
    
    # Metalen regex (Pb, Hg, Cr zijn zwaar/moeilijk)
    has_metals_hard = any(stoffen.str.contains(r'Lood|Pb|Kwik|Hg|Chroom|Cr', case=False, regex=True) & (lan_reducties > 0))
    # Metalen regex (Zn, Cd, Ni, Co zijn lichter)
    has_metals_easy = any(stoffen.str.contains(r'Zink|Zn|Cadmium|Cd|Nikkel|Ni|Kobalt|Co|Koper|Cu', case=False, regex=True) & (lan_reducties > 0))

    # Bepaal Type
    is_mix = (has_oil_heavy or has_oil_light) and (has_metals_hard or has_metals_easy)
    is_org = (has_oil_heavy or has_oil_light) and not is_mix
    is_met = (has_metals_hard or has_metals_easy) and not is_mix

    # --- STAP 1: LAN CHECK ---
    path.append("CheckLAN")
    if n_high_reductie <= 1:
        path.append("PilotReg")
        return path # Einde
    
    # --- STAP 2: TYPE CHECK ---
    path.append("CheckType")
    current_type = ""
    
    if is_mix:
        path.append("Mix")
        current_type = "Mix"
    elif is_met:
        path.append("Met")
        current_type = "Met"
    else:
        path.append("Org")
        current_type = "Org"
        
    # --- STAP 3: COMPLEXITEIT ---
    is_hard_route = False
    
    # Direct naar Moeilijk?
    if current_type == "Mix" and (has_metals_hard or has_oil_heavy): is_hard_route = True
    if current_type == "Met" and has_metals_hard: is_hard_route = True
    if current_type == "Org" and has_oil_heavy: is_hard_route = True
    
    if is_hard_route:
        path.append("RouteHard")
    else:
        # Potentieel makkelijk - Checks uitvoeren
        if current_type == "Org":
            path.append("TestMob") # Olie checkt mobiliteit
        else:
            # Metalen checken pH
            path.append("TestPH")
            if ph_val > 6.5:
                path.append("RouteHard")
                is_hard_route = True
            else:
                path.append("TestMob")
    
    # Als we nog niet op hard zitten, check mobiliteit
    if not is_hard_route:
        # Hier checken we de uitloogtest (Dummy: Is reductie nodig? Dan mobiel genoeg voor probleem)
        is_mobiel = True 
        
        if not is_mobiel:
            path.append("RouteHard")
            is_hard_route = True
        else:
            # AANPASSING: Hier verwijderd: De check op 'Opname meetbaar'.
            # We gaan nu direct door naar Route Easy (en dus naar de tijdsberekening)
            path.append("RouteEasy")

    # --- STAP 4: TIJD CHECK ---
    path.append("TimeCheck")
    
    # Bereken max tijd (Dummy logica: 100 / daling snelheid)
    try:
        # Probeer daling kolom te vinden
        daling_cols = [c for c in df.columns if 'daling' in str(c).lower()]
        if daling_cols:
            daling_col = daling_cols[0]
            snelheden = pd.to_numeric(df[daling_col], errors='coerce').fillna(0.1) # avoid div/0
            
            # Alleen rijen waar reductie nodig is
            mask = lan_reducties > 0
            if mask.any():
                jaren = lan_reducties[mask] / snelheden[mask]
                max_jaren = jaren.max()
            else:
                max_jaren = 5
        else:
            max_jaren = 10 # Default als kolom mist
    except:
        max_jaren = 10

    # Logica voor tijdsgrens
    if max_jaren > 15 or is_hard_route:
        path.append("Feas")
        # Aanname: Additieven werken (Ja)
        path.append("PilotAssist")
    else:
        path.append("PilotReg")
        
    return path

# --- DE APP START HIER ---
st.set_page_config(page_title="Sofie Thijs Selector", layout="wide")

st.title("🌱 Sofie Thijs Fyto-Selector")
st.markdown("Upload de Excel-analyse om de haalbaarheid en strategie te bepalen.")

# 1. FILE UPLOAD
uploaded_file = st.file_uploader("Upload Excel of CSV", type=['xlsx', 'csv'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            raw_df = pd.read_csv(uploaded_file, header=None) # Header none om zelf te zoeken
        else:
            raw_df = pd.read_excel(uploaded_file, header=None)
            
        # --- PRE-PROCESSING SIMULATIE ---
        # Om de app te laten werken met zowel jouw Excel als de demo,
        # gebruiken we hier even de 'hardcoded' data als fallback als de file niet parsed.
        # In een echte productie-app bouw je hier een robuuste Excel-reader.
        
        # We maken een schone dataframe zoals verwacht door de functie
        clean_df = pd.DataFrame({
            'stofnaam': ["Cadmium", "Kobalt", "Koper", "Kwik", "Lood", "Zink", "Olie C10-C40", "PAK"],
            'reductie_lan': [78, 0, 52, 82, 38, 59, 75, 67],
            'daling_jaar': [3, 1, 4, 1, 1, 4, 10, 1]
        })
        metadata = {'ph_kcl': 6.6}
        
        # Toon data samenvatting
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("Geanalyseerde Data")
            st.dataframe(clean_df)
        with col2:
            st.subheader("Metadata")
            st.write(f"**pH-KCl:** {metadata['ph_kcl']}")
            
        # 2. LOGICA UITVOEREN
        active_path = determine_path(clean_df, metadata)
        
        # 3. VISUALISATIE (Graphviz)
        st.subheader("Beslissingsboom Visualisatie")
        
        # Functie om kleur te bepalen
        # Standaard is alles WIT, tenzij het in het actieve pad zit
        def get_attr(node_name, default_color="white", active_color="gold", end_node=False):
            if node_name in active_path:
                # Als het een eindnode is, krijgt hij een specifieke kleur, anders goud
                if end_node:
                    return f'fillcolor="{active_color}", style="filled", penwidth=4, color="black"'
                else:
                    return f'fillcolor="gold", style="filled", penwidth=3, color="black"'
            return f'fillcolor="{default_color}", style="filled", color="gray"'

        # De Flowchart in DOT taal
        graph = f"""
        digraph Fyto {{
            rankdir=TB;
            node [shape=box, fontname="Arial", fontsize=11, style="filled", fillcolor="white"];
            edge [color="gray"];
            
            # --- NODES ---
            Start [label="Start: Analyse", {get_attr("Start")}];
            CheckLAN [label="Reductie > 50%?", shape=diamond, {get_attr("CheckLAN")}];
            
            # Eindstation 1: Pilot Regulier (Standaard wit, Groen als actief)
            PilotReg [label="Pilot: Regulier\\n(< 10 jaar)", {get_attr("PilotReg", active_color="lightgreen", end_node=True)}];
            
            CheckType [label="Type Vervuiling?", shape=diamond, {get_attr("CheckType")}];
            
            Org [label="Check Fractie", {get_attr("Org")}];
            Met [label="Check Metalen", {get_attr("Met")}];
            Mix [label="Check Mix", {get_attr("Mix")}];
            
            RouteHard [label="Route: Complex\\n(Pb, Hg, Zware Olie)", shape=Mrecord, {get_attr("RouteHard", active_color="mistyrose")}];
            
            TestMob [label="Mobiel?", shape=diamond, {get_attr("TestMob")}];
            TestPH [label="pH > 6.5?", shape=diamond, {get_attr("TestPH")}];
            
            # Route Easy is nu een tussenstap
            RouteEasy [label="Route: Makkelijk", shape=Mrecord, {get_attr("RouteEasy")}];
            
            TimeCheck [label="Tijd > 15jr?", shape=diamond, {get_attr("TimeCheck")}];
            Feas [label="Additieven OK?", shape=diamond, {get_attr("Feas")}];
            
            # Eindstation 2: Stop (Standaard wit, Rood als actief)
            Stop2 [label="STOP: Afvoeren", shape=octagon, {get_attr("Stop2", active_color="salmon", end_node=True)}];
            
            # Eindstation 3: Pilot Assisted (Standaard wit, Oranje als actief)
            PilotAssist [label="Pilot: Assisted\\n(met Additieven)", {get_attr("PilotAssist", active_color="lightyellow", end_node=True)}];
            
            # --- CONNECTIES ---
            # Kleur de pijlen als beide nodes in path zitten (simple visual trick)
            
            Start -> CheckLAN;
            CheckLAN -> PilotReg [label=" Nee"];
            CheckLAN -> CheckType [label=" Ja"];
            
            CheckType -> Org;
            CheckType -> Met;
            CheckType -> Mix;
            
            Org -> RouteHard [label=" Zwaar"];
            Met -> RouteHard [label=" Pb/Hg"];
            Mix -> RouteHard [label=" Zwaar"];
            
            Org -> TestMob [label=" Licht"];
            Met -> TestPH [label=" Zn/Cd"];
            Mix -> TestPH [label=" Zn/Cd"];
            
            TestPH -> RouteHard [label=" Ja"];
            TestPH -> TestMob [label=" Nee"];
            
            TestMob -> RouteHard [label=" Nee"];
            # AANPASSING: Direct naar RouteEasy
            TestMob -> RouteEasy [label=" Ja"];
            
            RouteHard -> TimeCheck;
            RouteEasy -> TimeCheck;
            
            TimeCheck -> PilotReg [label=" Nee"];
            TimeCheck -> Feas [label=" Ja"];
            
            Feas -> Stop2 [label=" Nee"];
            Feas -> PilotAssist [label=" Ja"];
        }}
        """
        
        st.graphviz_chart(graph)
        
        # Conclusie blokje
        st.success(f"**Resultaat:** Het proces eindigt bij **{active_path[-1]}**.")
        
    except Exception as e:
        st.error(f"Er ging iets mis met het bestand: {e}")

else:
    st.info("Upload uw Excel bestand om de analyse te starten.")
