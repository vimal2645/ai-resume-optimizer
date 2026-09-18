<div align="center">
  <img src="https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/Python-Dark.svg" alt="Python" width="50" height="50"/>
  <img src="https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/Streamlit-Dark.svg" alt="Streamlit" width="50" height="50"/>
  
  <h1>🎯 AI Resume Optimizer</h1>
  <p><strong>An LLM-Free, In-Place Resume Optimization Engine</strong></p>
</div>

---

**AI Resume Optimizer** is a powerful web application that helps job seekers perfectly align their resumes with target job descriptions. Built entirely with local parsing and TF-IDF similarity algorithms, it provides instant ATS scoring, identifies missing skills, and seamlessly injects them directly into your original resume document—all while keeping your data 100% private and API-cost free.

## ✨ Features

- **📊 Advanced ATS Scoring:** Calculates a weighted compatibility score based on Skill Matching (60%) and TF-IDF Similarity (40%).
- **🧠 Intelligent Role Detection:** Automatically identifies the target job archetype and adjusts the required skills dynamically.
- **🏷️ Skill Classification:** Categorizes skills into three buckets: *Already Listed*, *Will Be Added* (Optimizable), and *Genuinely Missing*.
- **🪄 In-Place Resume Editing:** Upload your DOCX or PDF, and the engine will surgically inject missing skills into your existing "Skills" section without destroying the original formatting.
- **📝 Automated Cover Letters:** Generates a custom cover letter document based on your resume and the target role.
- **📈 Detailed ATS Reports:** Download a comprehensive DOCX report of your keyword matches and gaps.
- **🎨 Modern UI:** A highly polished, dynamic Streamlit interface featuring 3D ambient animations, glassmorphism, and responsive metric cards.

## 🛠️ Tech Stack

- **Frontend & UI:** [Streamlit](https://streamlit.io/) (Enhanced with custom HTML/CSS for advanced styling)
- **Language:** Python 3.10+
- **Core Processing:** 
  - `pypdf` & `python-docx` for document parsing and modification
  - `flashtext` for hyper-fast keyword extraction
  - `scikit-learn` for TF-IDF vectorization and cosine similarity
- **Deployment:** Fully compatible with Streamlit Community Cloud, Hugging Face Spaces, or any Dockerized PaaS.

## 🚀 Getting Started

### Prerequisites

Ensure you have Python 3 installed on your machine. 

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/ai-resume-optimizer.git
   cd ai-resume-optimizer
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   streamlit run app.py
   ```
   The app will instantly open in your default browser at `http://localhost:8501`.

## 📂 Project Structure

- `app.py`: The main Streamlit frontend application.
- `core/`: Contains the core parsing logic (`parser.py`) and role detection algorithms (`role_detector.py`).
- `utils/`: Utility scripts for document generation (`document_generator.py`), in-place editing (`inplace_editor.py`), and skill matching (`ai_skill_matcher.py`).
- `data/`: Local JSON databases for skills, synonyms, and role archetypes.
- `.github/workflows/`: Contains GitHub Actions (e.g., `keep_alive.yml` to prevent cloud platforms from sleeping).

## 🔒 Privacy First
Unlike many AI tools that send your highly sensitive personal data to OpenAI or Anthropic, this application runs entirely locally. It utilizes a vast, curated internal database of tech skills and advanced Natural Language Processing to score and edit your resume securely.

---
<div align="center">
  <i>Built to help you land your dream job faster.</i>
</div>
