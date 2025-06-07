++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

Based on input:

Job Dependencies:

JOB_A → JOB_B, JOB_C, JOB_F_FAILED
JOB_B → JOB_D_LONG_RUNNING
JOB_C & JOB_D_LONG_RUNNING → JOB_E_FINAL
JOB_F_FAILED → JOB_G_IMPACTED
JOB_H_STANDALONE (no dependencies)

++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

Status Visualization:

🟢 Green: JOB_A, JOB_B, JOB_C, JOB_H_STANDALONE (SUCCESS)
🟡 Amber: JOB_D_LONG_RUNNING (RUNNING) + dependent JOB_E_FINAL
🔴 Red: JOB_F_FAILED (FAILED) + impacted JOB_G_IMPACTED
🔵 Cyan: JOB_E_FINAL (ACTIVATED - waiting for dependencies)
⚫ Gray: JOB_G_IMPACTED (INACTIVE due to failed dependency)

++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

How to Run

Save the code as autosys_dashboard.py
Install requirements: pip install streamlit pandas networkx plotly numpy
Run: streamlit run autosys_dashboard.py
Upload your sample_jobs.jil and sample_autorep.txt files
Click "Process Files"

The dashboard will now correctly parse your files and show the dependency graph with proper color coding based on job statuses!


