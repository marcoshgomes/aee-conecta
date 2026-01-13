import streamlit as st
import pandas as pd
import os
import hashlib
import time
from supabase import create_client, Client
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
from datetime import datetime
from PIL import Image

# --- 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR ---
st.set_page_config(page_title="AEE Conecta", layout="centered", page_icon="💠")

st.markdown(
    """
    <head><meta name="google" content="notranslate"></head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
    """,
    unsafe_allow_html=True
)

# --- 2. CONEXÃO COM A NUVEM (SUPABASE) ---
# Certifique-se que instalou: pip install supabase
try:
    URL = st.secrets["supabase"]["url"]
    KEY = st.secrets["supabase"]["key"]
    supabase: Client = create_client(URL, KEY)
except Exception as e:
    st.error("Erro nas credenciais do Supabase. Verifique o arquivo secrets.toml")
    st.stop()

# Garantir pastas locais para cache de fotos
for f in ["fotos_alunos", "fotos_relatorios"]:
    if not os.path.exists(f): os.makedirs(f)

# --- 3. FUNÇÕES DE APOIO ---
def hash_pw(senha):
    return hashlib.sha256(str(senha).encode()).hexdigest()

def registrar_log(rf):
    try:
        supabase.table("logs").insert({"rf": rf, "data_hora": datetime.now().strftime('%d/%m/%Y %H:%M:%S')}).execute()
    except: pass

@st.cache_data(ttl=5)
def load_excel():
    try:
        df_p = pd.read_excel("cadastro_AEE.xlsx", sheet_name="professores")
        df_a = pd.read_excel("cadastro_AEE.xlsx", sheet_name="alunos")
        for df in [df_p, df_a]:
            df.columns = [c.lower().strip() for c in df.columns]
            for col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        return df_p, df_a
    except Exception as e:
        st.error(f"Erro ao carregar Excel: {e}")
        return pd.DataFrame(), pd.DataFrame()

# --- 4. FUNÇÕES DE GERAÇÃO DE WORD ---
def gerar_folha_rosto(dados):
    doc = Document()
    h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.add_run("CEU EMEF Prof.ª MARA CRISTINA TARTAGLIA SENA\nAEE - ATENDIMENTO EDUCACIONAL ESPECIALIZADO\nREGISTRO - ATIVIDADE FLEXIBILIZADA").bold = True
    doc.add_paragraph(f"ANO LETIVO {datetime.now().year}").alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    f_path = os.path.join("fotos_alunos", str(dados.get('foto', '')))
    if os.path.exists(f_path) and str(dados.get('foto', '')) != 'nan':
        doc.add_picture(f_path, width=Inches(3)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    t = doc.add_table(rows=4, cols=1); t.style = 'Table Grid'
    t.rows[0].cells[0].text = f"ESTUDANTE: {dados.get('aluno', 'N/A')}"
    t.rows[1].cells[0].text = f"TURMA: {dados.get('turma', 'N/A')}"
    col_nec = next((x for x in list(dados.index) if "nec" in x), "necessidades")
    t.rows[2].cells[0].text = f"DEFICIÊNCIA/CONDIÇÃO: {dados.get(col_nec, 'N/A')}"
    t.rows[3].cells[0].text = f"DATA DE NASCIMENTO: {dados.get('data_nascimento', 'N/A')}"
    
    doc.add_heading('OBSERVAÇÕES DO PROFESSOR:', level=3); doc.add_paragraph(str(dados.get('observacoes_gerais', '')))
    buf = BytesIO(); doc.save(buf); buf.seek(0); return buf

def gerar_relatorio_aula(df_rels, nome_aluno, turma_aluno, df_todos_professores):
    doc = Document()
    for i, row in df_rels.iterrows():
        rf_aula = row['rf_professor']
        filtro_p = df_todos_professores[df_todos_professores['rf'] == rf_aula]
        nome_p = filtro_p.iloc[0]['professor'] if not filtro_p.empty else "Professor não identificado"

        h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        h.add_run("CEU EMEF Prof.ª MARA CRISTINA TARTAGLIA SENA\nAEE - ATENDIMENTO EDUCACIONAL ESPECIALIZADO\nREGISTRO - ATIVIDADE FLEXIBILIZADA").bold = True
        p_title = doc.add_paragraph(); p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.add_run(f"{row['bimestre']} – ANO LETIVO {datetime.now().year}").bold = True
        
        doc.add_paragraph(f"ESTUDANTE: {nome_aluno}\nTURMA: {turma_aluno}")
        doc.add_paragraph(f"PROFESSOR: {nome_p} | DISCIPLINA/TEMA: {row.get('disciplina_tema', 'N/A')}")
        
        p_sim = "x" if row.get('participou_aula') == "Sim" else " "
        p_nao = "x" if row.get('participou_aula') == "Não" else " "
        p_part = doc.add_paragraph(f"O ESTUDANTE PARTICIPOU DA SUA AULA? ( {p_sim} ) SIM ( {p_nao} ) NÃO.")
        if row.get('participou_aula') == "Não": p_part.add_run(f" RELATE O MOTIVO: {row.get('motivo_nao_participou', '')}")
        
        doc.add_heading('ATIVIDADES PLANEJADAS:', level=3); doc.add_paragraph(str(row['planejado']))
        doc.add_heading('ATIVIDADE REALIZADA COM O ESTUDANTE:', level=3); doc.add_paragraph(str(row['realizado']))
        
        if row['foto_path']:
            try:
                res_foto = supabase.storage.from_("fotos_aee").download(row['foto_path'])
                doc.add_picture(BytesIO(res_foto), width=Inches(3.5)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except: pass
        
        doc.add_heading('COMO FOI A PARTICIPAÇÃO DO ESTUDANTE?', level=3)
        parts = str(row['participacao']).split(", ")
        opcoes = ["REALIZOU COM AUTONOMIA", "REALIZOU COM APOIO E INTERVENÇÃO DE UM ADULTO", "REALIZOU COM APOIO DE UM COLEGA", "NÃO REALIZOU"]
        for op in opcoes:
            check = "x" if op in parts else " "
            doc.add_paragraph(f"( {check} ) {op}")
        
        doc.add_paragraph(f"\nDATA DE REALIZAÇÃO DA ATIVIDADE: {row['data']}")
        if i < len(df_rels) - 1: doc.add_page_break()
    buf = BytesIO(); doc.save(buf); buf.seek(0); return buf

# --- 5. SISTEMA DE LOGIN ---
df_prof, df_alunos = load_excel()

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "change_pw" not in st.session_state: st.session_state.change_pw = False

if not st.session_state.logged_in:
    st.title("💠 AEE Conecta - Login")
    rf_in = st.text_input("RF").strip()
    pw_in = st.text_input("Senha", type="password").strip()

    if st.button("Entrar"):
        user_excel = df_prof[df_prof['rf'] == rf_in]
        if not user_excel.empty:
            res = supabase.table("credenciais").select("senha_hash").eq("rf", rf_in).execute()
            if not res.data:
                if pw_in == rf_in:
                    st.session_state.change_pw, st.session_state.temp_rf = True, rf_in
                    st.rerun()
                else: st.error("Primeiro acesso? Use seu RF como senha.")
            else:
                if hash_pw(pw_in) == res.data[0]['senha_hash']:
                    st.session_state.logged_in = True
                    st.session_state.u_rf, st.session_state.u_nome = rf_in, user_excel.iloc[0]['professor']
                    st.session_state.u_perfil = str(user_excel.iloc[0]['perfil']).lower()
                    registrar_log(rf_in); st.rerun()
                else: st.error("Senha incorreta.")
        else: st.error("RF não cadastrado.")

    if st.session_state.change_pw:
        st.divider()
        st.warning("⚠️ CADASTRE UMA SENHA PESSOAL")
        n_pw = st.text_input("Nova Senha (mín. 6 carac.)", type="password")
        c_pw = st.text_input("Confirme a Senha", type="password")
        if st.button("Salvar Nova Senha"):
            if len(n_pw) >= 6 and n_pw == c_pw:
                supabase.table("credenciais").insert({"rf": st.session_state.temp_rf, "senha_hash": hash_pw(n_pw)}).execute()
                st.session_state.change_pw = False
                st.toast("✅ Senha cadastrada com sucesso!"); time.sleep(1.5); st.rerun()
            else: st.error("Senhas inválidas ou curtas.")

else:
    # --- 6. INTERFACE PRINCIPAL ---
    st.sidebar.title(f"Olá, {st.session_state.u_nome}")
    menu = st.sidebar.radio("Navegação", ["Início", "Lançar Relatório", "Painel Gestor", "Sair"])

    if menu == "Sair":
        st.session_state.logged_in = False
        st.rerun()

    if menu == "Início":
        st.title("🏠 Bem-vindo ao AEE Conecta")
        st.markdown(f"### Olá, {st.session_state.u_nome}!")
        st.divider()
        st.info("""
        Este sistema foi desenvolvido para simplificar o registro e a gestão dos atendimentos do AEE.
        
        **Como utilizar:**
        *   **Professores:** Utilize o menu ao lado e clique em **Lançar Relatório** para registrar suas aulas.
        *   **Gestores:** Acesse o **Painel Gestor** para baixar Folhas de Rosto e consolidar relatórios bimestrais em Word.
        """)
        st.success("Selecione uma opção no menu lateral para começar.")
        st.markdown("<br><br><br><div style='text-align: center; color: #888888; font-size: 0.9em; border-top: 1px solid #eeeeee; padding-top: 20px;'><b>By Prof. Marcão</b><br>Software de apoio pedagógico - Freeware</div>", unsafe_allow_html=True)

    elif menu == "Lançar Relatório":
        st.header("📝 Lançar Relatório de Aula")
        if "form_id" not in st.session_state: st.session_state.form_id = 0
        lista_est = ["Selecione o Estudante..."] + sorted(df_alunos['aluno'].tolist())
        al_sel = st.selectbox("Escolha o aluno:", lista_est, key=f"sel_{st.session_state.form_id}")

        if al_sel != "Selecione o Estudante...":
            al_inf = df_alunos[df_alunos['aluno'] == al_sel].iloc[0]
            with st.container(border=True):
                st.subheader(f"Aluno: {al_sel}")
                dt = st.date_input("Data", datetime.now())
                bm = st.selectbox("Bimestre", ["1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"])
                tm = st.text_input("Disciplina/Tema")
                p_a = st.radio("O estudante participou da aula?", ["Sim", "Não"], horizontal=True)
                mot = st.text_area("Se 'Não', relate o motivo:") if p_a == "Não" else ""
                pl = st.text_area("Atividades Planejadas")
                re = st.text_area("Atividades Realizadas")
                pn = st.multiselect("Nível de Participação:", ["REALIZOU COM AUTONOMIA", "REALIZOU COM APOIO E INTERVENÇÃO DE UM ADULTO", "REALIZOU WITH APOIO DE UM COLEGA", "NÃO REALIZOU"])
                ft = st.file_uploader("Anexar foto")
                
                if st.button("Salvar Registro"):
                    path_f = ""
                    if ft:
                        path_f = f"aula_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                        supabase.storage.from_("fotos_aee").upload(path_f, ft.getvalue())
                    
                    supabase.table("relatorios").insert({
                        "data": dt.strftime('%d/%m/%Y'), "rf_professor": st.session_state.u_rf, "registro_aluno": str(al_inf['registro']),
                        "bimestre": bm, "participou_aula": p_a, "motivo_nao_participou": mot, "disciplina_tema": tm, "planejado": pl,
                        "realizado": re, "participacao": ", ".join(pn), "foto_path": path_f
                    }).execute()
                    
                    st.toast("✅ Salvando relatório!")
                    time.sleep(1.5); st.session_state.form_id += 1; st.rerun()

    elif menu == "Painel Gestor":
        if st.session_state.u_perfil != "gestor": st.error("Acesso restrito.")
        else:
            st.title("⚙️ Painel de Gestão")
            tab1, tab2 = st.tabs(["📄 Documentos", "🔒 Segurança e Acessos"])
            with tab1:
                al_f = st.selectbox("Selecione o Aluno", sorted(df_alunos['aluno'].tolist()), key="gest_sel")
                d_f = df_alunos[df_alunos['aluno'] == al_f].iloc[0]
                c1, c2 = st.columns(2)
                c1.download_button("📥 Baixar Folha de Rosto", gerar_folha_rosto(d_f), f"Rosto_{al_f}.docx")
                
                bim_f = st.selectbox("Filtrar Bimestre", ["Todos", "1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"])
                res = supabase.table("relatorios").select("*").eq("registro_aluno", str(d_f['registro'])).execute()
                df_final = pd.DataFrame(res.data)
                if not df_final.empty:
                    if bim_f != "Todos": df_final = df_final[df_final['bimestre'] == bim_f]
                    if not df_final.empty:
                        c2.download_button(f"📥 Baixar Relatórios ({len(df_final)})", gerar_relatorio_aula(df_final, al_f, d_f['turma'], df_prof), f"Relatos_{al_f}.docx")
            
            with tab2:
                prof_r = st.selectbox("Escolha o professor para resetar senha:", sorted(df_prof['professor'].tolist()))
                rf_r = df_prof[df_prof['professor'] == prof_r].iloc[0]['rf']
                if st.button("Resetar Senha deste Professor"):
                    supabase.table("credenciais").delete().eq("rf", rf_r).execute()
                    st.warning("Senha resetada para o padrão (RF).")
                st.divider()
                logs_res = supabase.table("logs").select("*").order("id", desc=True).limit(50).execute()
                if logs_res.data:
                    logs_df = pd.DataFrame(logs_res.data).merge(df_prof[['rf', 'professor']], on='rf', how='left')
                    st.dataframe(logs_df[['data_hora', 'professor', 'rf']], use_container_width=True)