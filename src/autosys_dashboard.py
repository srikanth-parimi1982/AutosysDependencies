import streamlit as st
import pandas as pd
import networkx as nx
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import re
import io
from collections import defaultdict, deque
import numpy as np
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Autosys Job Dependency Dashboard",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

class AutosysParser:
    """Parser for Autosys JIL scripts and job status reports"""
    
    def __init__(self):
        self.jobs = {}
        self.dependencies = defaultdict(list)
        self.job_status = {}
    
    def parse_jil_script(self, jil_content):
        """Parse JIL script to extract job definitions and dependencies"""
        current_job = None
        
        for line in jil_content.split('\n'):
            line = line.strip()
            
            # Job definition
            if line.startswith('insert_job:'):
                current_job = line.split(':', 1)[1].strip()
                self.jobs[current_job] = {
                    'name': current_job,
                    'job_type': 'cmd',
                    'command': '',
                    'condition': '',
                    'description': '',
                    'machine': '',
                    'owner': ''
                }
            
            elif current_job and ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                if key == 'job_type':
                    self.jobs[current_job]['job_type'] = value
                elif key == 'command':
                    self.jobs[current_job]['command'] = value
                elif key == 'condition':
                    self.jobs[current_job]['condition'] = value
                    # Parse dependencies from condition
                    self._parse_condition(current_job, value)
                elif key == 'description':
                    self.jobs[current_job]['description'] = value
                elif key == 'machine':
                    self.jobs[current_job]['machine'] = value
                elif key == 'owner':
                    self.jobs[current_job]['owner'] = value
    
    def _parse_condition(self, job_name, condition):
        """Extract job dependencies from condition statement"""
        if not condition:
            return
        
        # Look for success/done/failure conditions
        # Pattern: success(job_name) or done(job_name) or failure(job_name)
        patterns = [
            r'success\(([^)]+)\)',
            r'done\(([^)]+)\)',
            r'failure\(([^)]+)\)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, condition, re.IGNORECASE)
            for match in matches:
                parent_job = match.strip()
                if parent_job != job_name:  # Avoid self-dependency
                    self.dependencies[parent_job].append(job_name)
    
    def parse_autorep_output(self, autorep_content):
        """Parse autorep -J output to get job status information"""
        lines = autorep_content.strip().split('\n')
        
        for line in lines:
            if line.strip() and not line.startswith('Job Name'):
                # Handle fixed-width format - extract by position
                if len(line) > 60:  # Ensure line has enough characters
                    # Extract job name (first 60+ characters, then strip)
                    job_name = line[:60].strip()
                    
                    # Extract remaining parts
                    remaining = line[60:].strip()
                    parts = remaining.split()
                    
                    if len(parts) >= 3:
                        last_start = parts[0] + ' ' + parts[1] if len(parts) > 1 else parts[0]
                        last_end = parts[2] + ' ' + parts[3] if len(parts) > 3 and parts[2] != '-----' else parts[2]
                        status = parts[4] if len(parts) > 4 else 'UNKNOWN'
                        
                        # Map common status codes
                        status_mapping = {
                            'SU': 'SUCCESS',
                            'RU': 'RUNNING', 
                            'FA': 'FAILED',
                            'TE': 'TERMINATED',
                            'IN': 'INACTIVE',
                            'AC': 'ACTIVATED',
                            'OH': 'ON_HOLD',
                            'ST': 'STARTING'
                        }
                        
                        mapped_status = status_mapping.get(status.upper(), status.upper())
                        
                        self.job_status[job_name] = {
                            'status': mapped_status,
                            'last_start': last_start if last_start != '-----' else 'Not Started',
                            'last_end': last_end if last_end != '-----' else 'Not Completed'
                        }
                else:
                    # Fallback for shorter lines
                    parts = line.split()
                    if len(parts) >= 1:
                        job_name = parts[0]
                        status = parts[-1] if len(parts) > 1 else 'UNKNOWN'
                        
                        self.job_status[job_name] = {
                            'status': status.upper(),
                            'last_start': 'Unknown',
                            'last_end': 'Unknown'
                        }

class NetworkVisualizer:
    """Create network visualization for job dependencies"""
    
    def __init__(self, jobs, dependencies, job_status):
        self.jobs = jobs
        self.dependencies = dependencies
        self.job_status = job_status
        self.graph = nx.DiGraph()
        self.status_colors = {
            'SUCCESS': '#28a745',     # Green
            'RUNNING': '#ffc107',     # Amber
            'FAILED': '#dc3545',      # Red
            'TERMINATED': '#dc3545',  # Red
            'INACTIVE': '#6c757d',    # Gray
            'ACTIVATED': '#17a2b8',   # Cyan
            'ON_HOLD': '#17a2b8',     # Cyan
            'STARTING': '#fd7e14',    # Orange
            'UNKNOWN': '#6f42c1'      # Purple
        }
    
    def build_graph(self):
        """Build NetworkX graph from job dependencies"""
        # Add all jobs as nodes
        for job_name in self.jobs:
            status = self.job_status.get(job_name, {}).get('status', 'UNKNOWN')
            self.graph.add_node(job_name, status=status)
        
        # Add edges for dependencies
        for parent_job, dependent_jobs in self.dependencies.items():
            for dependent_job in dependent_jobs:
                if parent_job in self.jobs and dependent_job in self.jobs:
                    self.graph.add_edge(parent_job, dependent_job)
    
    def get_impacted_jobs(self, job_name, status):
        """Get list of jobs that could be impacted by a job's status"""
        impacted = set()
        
        if status in ['FAILED', 'TERMINATED']:
            # Get all downstream dependencies
            if job_name in self.graph:
                descendants = nx.descendants(self.graph, job_name)
                impacted.update(descendants)
        elif status == 'RUNNING':
            # Get immediate downstream dependencies
            if job_name in self.graph:
                successors = list(self.graph.successors(job_name))
                impacted.update(successors)
        
        return impacted
    
    def create_plotly_visualization(self):
        """Create interactive Plotly network visualization"""
        if not self.graph.nodes():
            return go.Figure()
        
        # Use spring layout for better visualization
        pos = nx.spring_layout(self.graph, k=3, iterations=50)
        
        # Prepare node data
        node_x = [pos[node][0] for node in self.graph.nodes()]
        node_y = [pos[node][1] for node in self.graph.nodes()]
        
        # Prepare edge data
        edge_x = []
        edge_y = []
        for edge in self.graph.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
        
        # Create edge trace
        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=2, color='#888'),
            hoverinfo='none',
            mode='lines'
        )
        
        # Create node trace
        node_colors = []
        node_text = []
        hover_text = []
        
        for node in self.graph.nodes():
            status = self.job_status.get(node, {}).get('status', 'UNKNOWN')
            color = self.status_colors.get(status, '#6f42c1')
            node_colors.append(color)
            
            # Node labels
            node_text.append(node)
            
            # Hover information
            job_info = self.jobs.get(node, {})
            hover_info = f"<b>{node}</b><br>"
            hover_info += f"Status: {status}<br>"
            hover_info += f"Type: {job_info.get('job_type', 'Unknown')}<br>"
            hover_info += f"Machine: {job_info.get('machine', 'Unknown')}<br>"
            if job_info.get('description'):
                hover_info += f"Description: {job_info['description']}<br>"
            
            # Show impacted jobs
            impacted = self.get_impacted_jobs(node, status)
            if impacted:
                hover_info += f"Impacted Jobs: {', '.join(list(impacted)[:5])}"
                if len(impacted) > 5:
                    hover_info += f" (+{len(impacted)-5} more)"
            
            hover_text.append(hover_info)
        
        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            hoverinfo='text',
            hovertext=hover_text,
            text=node_text,
            textposition="middle center",
            textfont=dict(size=10, color="white"),
            marker=dict(
                size=20,
                color=node_colors,
                line=dict(width=2, color="white")
            )
        )
        
        # Create figure
        fig = go.Figure(data=[edge_trace, node_trace],
                       layout=go.Layout(
                           title=dict(text="Autosys Job Dependency Network", font=dict(size=16)),
                           showlegend=False,
                           hovermode='closest',
                           margin=dict(b=20,l=5,r=5,t=40),
                           annotations=[ dict(
                               text="Hover over nodes for details. Colors indicate job status.",
                               showarrow=False,
                               xref="paper", yref="paper",
                               x=0.005, y=-0.002,
                               xanchor="left", yanchor="bottom",
                               font=dict(color="#888", size=12)
                           )],
                           xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                           yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                           plot_bgcolor='white'
                       ))
        
        return fig

def main():
    st.title("🔄 Autosys Job Dependency Dashboard")
    st.markdown("---")
    
    # Initialize session state
    if 'parser' not in st.session_state:
        st.session_state.parser = AutosysParser()
    if 'visualizer' not in st.session_state:
        st.session_state.visualizer = None
    
    # Sidebar for file uploads
    with st.sidebar:
        st.header("📁 File Upload")
        
        # JIL Script Upload
        st.subheader("1. Autosys JIL Script")
        jil_file = st.file_uploader(
            "Upload consolidated JIL script",
            type=['jil', 'txt'],
            key="jil_upload"
        )
        
        # Autorep Output Upload
        st.subheader("2. Job Status Report")
        autorep_file = st.file_uploader(
            "Upload autorep -J output",
            type=['txt', 'log'],
            key="autorep_upload"
        )
        
        # Process files
        if st.button("🔄 Process Files", type="primary"):
            if jil_file and autorep_file:
                with st.spinner("Processing files..."):
                    # Parse JIL script
                    jil_content = jil_file.read().decode('utf-8')
                    st.session_state.parser.parse_jil_script(jil_content)
                    
                    # Parse autorep output
                    autorep_content = autorep_file.read().decode('utf-8')
                    st.session_state.parser.parse_autorep_output(autorep_content)
                    
                    # Create visualizer
                    st.session_state.visualizer = NetworkVisualizer(
                        st.session_state.parser.jobs,
                        st.session_state.parser.dependencies,
                        st.session_state.parser.job_status
                    )
                    st.session_state.visualizer.build_graph()
                    
                st.success("✅ Files processed successfully!")
            else:
                st.error("❌ Please upload both files.")
    
    # Main content area
    if st.session_state.visualizer:
        # Create tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            "🌐 Dependency Graph", 
            "📊 Job Statistics", 
            "🔍 Job Details", 
            "⚠️ Impact Analysis"
        ])
        
        with tab1:
            st.subheader("Job Dependency Network")
            
            # Status legend
            col1, col2 = st.columns([3, 1])
            
            with col2:
                st.markdown("**Status Legend:**")
                legend_html = """
                <div style='font-size: 12px;'>
                <span style='color: #28a745;'>●</span> SUCCESS<br>
                <span style='color: #ffc107;'>●</span> RUNNING<br>
                <span style='color: #dc3545;'>●</span> FAILED/TERMINATED<br>
                <span style='color: #6c757d;'>●</span> INACTIVE<br>
                <span style='color: #17a2b8;'>●</span> ACTIVATED/ON_HOLD<br>
                <span style='color: #fd7e14;'>●</span> STARTING<br>
                <span style='color: #6f42c1;'>●</span> UNKNOWN<br>
                </div>
                """
                st.markdown(legend_html, unsafe_allow_html=True)
            
            with col1:
                # Create and display the network graph
                fig = st.session_state.visualizer.create_plotly_visualization()
                st.plotly_chart(fig, use_container_width=True, height=600)
        
        with tab2:
            st.subheader("Job Execution Statistics")
            
            # Status distribution
            status_counts = defaultdict(int)
            for job_name, status_info in st.session_state.parser.job_status.items():
                status_counts[status_info['status']] += 1
            
            if status_counts:
                # Create pie chart
                fig_pie = px.pie(
                    values=list(status_counts.values()),
                    names=list(status_counts.keys()),
                    title="Job Status Distribution"
                )
                st.plotly_chart(fig_pie, use_container_width=True)
                
                # Create bar chart
                fig_bar = px.bar(
                    x=list(status_counts.keys()),
                    y=list(status_counts.values()),
                    title="Job Count by Status"
                )
                st.plotly_chart(fig_bar, use_container_width=True)
        
        with tab3:
            st.subheader("Detailed Job Information")
            
            # Job selection
            job_names = list(st.session_state.parser.jobs.keys())
            selected_job = st.selectbox("Select a job to view details:", job_names)
            
            if selected_job:
                job_info = st.session_state.parser.jobs[selected_job]
                status_info = st.session_state.parser.job_status.get(selected_job, {})
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Job Configuration:**")
                    st.json(job_info)
                
                with col2:
                    st.markdown("**Execution Status:**")
                    st.json(status_info)
                
                # Dependencies
                st.markdown("**Dependencies:**")
                dependencies = st.session_state.parser.dependencies.get(selected_job, [])
                if dependencies:
                    st.write(f"This job depends on: {', '.join(dependencies)}")
                else:
                    st.write("No dependencies found.")
                
                # Dependent jobs
                dependents = []
                for parent, deps in st.session_state.parser.dependencies.items():
                    if selected_job in deps:
                        dependents.append(parent)
                
                if dependents:
                    st.write(f"Jobs that depend on this job: {', '.join(dependents)}")
                else:
                    st.write("No jobs depend on this job.")
        
        with tab4:
            st.subheader("Impact Analysis")
            
            # Find problematic jobs
            failed_jobs = []
            running_jobs = []
            
            for job_name, status_info in st.session_state.parser.job_status.items():
                status = status_info['status']
                if status in ['FAILED', 'TERMINATED']:
                    failed_jobs.append(job_name)
                elif status == 'RUNNING':
                    running_jobs.append(job_name)
            
            if failed_jobs:
                st.error("🚨 **Failed/Terminated Jobs and Their Impact:**")
                for job in failed_jobs:
                    impacted = st.session_state.visualizer.get_impacted_jobs(job, 'FAILED')
                    st.write(f"**{job}** - Potentially impacts {len(impacted)} downstream jobs")
                    if impacted:
                        st.write(f"   → {', '.join(list(impacted)[:10])}")
                        if len(impacted) > 10:
                            st.write(f"   → ... and {len(impacted)-10} more jobs")
            
            if running_jobs:
                st.warning("⏳ **Currently Running Jobs:**")
                for job in running_jobs:
                    impacted = st.session_state.visualizer.get_impacted_jobs(job, 'RUNNING')
                    st.write(f"**{job}** - {len(impacted)} jobs waiting for completion")
                    if impacted:
                        st.write(f"   → {', '.join(list(impacted)[:10])}")
                        if len(impacted) > 10:
                            st.write(f"   → ... and {len(impacted)-10} more jobs")
            
            if not failed_jobs and not running_jobs:
                st.success("✅ No critical issues detected in the current job execution state.")
    
    else:
        # Welcome screen
        st.markdown("""
        ## Welcome to the Autosys Job Dependency Dashboard
        
        This application helps you visualize and analyze Autosys job dependencies and their execution status.
        
        ### How to use:
        1. **Upload JIL Script**: Upload your consolidated Autosys JIL script file
        2. **Upload Status Report**: Upload the output from `autorep -J` command
        3. **Click Process Files**: The system will parse both files and create visualizations
        4. **Explore**: Use the tabs to explore dependencies, statistics, and impact analysis
        
        ### Features:
        - 🌐 **Interactive Dependency Graph**: Visual network showing job relationships
        - 📊 **Job Statistics**: Distribution of job statuses and execution metrics
        - 🔍 **Detailed Job Information**: Complete job configuration and status details
        - ⚠️ **Impact Analysis**: Identify which jobs are affected by failures or delays
        
        ### Color Coding:
        - 🟢 **Green**: Successfully completed jobs
        - 🟡 **Amber**: Currently running jobs (and their dependents)
        - 🔴 **Red**: Failed or terminated jobs (and their dependents)
        - 🔵 **Blue**: Jobs on hold
        - 🟣 **Purple**: Unknown status
        - ⚫ **Gray**: Inactive jobs
        """)

if __name__ == "__main__":
    main()