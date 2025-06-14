import pandas as pd
import io
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os


def analyze_test_data():
    """
    Lädt die CSV-Datei, führt eine detaillierte Analyse durch, erstellt Diagramme
    und visualisiert die zusammengefassten Performanz- und Genauigkeits-Metriken.
    """
    # --- 1. Datenaufbereitung ---
    file_path = 'Nutzertests_Auswertung.csv'

    if not os.path.exists(file_path):
        print(f"FEHLER: Die Datei '{file_path}' wurde nicht im selben Verzeichnis gefunden.")
        return

    try:
        df = pd.read_csv(file_path, delimiter=';', encoding='latin-1')
        print("Datei erfolgreich geladen.")
    except Exception as e:
        print(f"Ein Fehler ist beim Laden der CSV-Datei aufgetreten: {e}")
        return

    df.columns = df.columns.str.strip()
    numeric_cols = [
        'Task_Completion_Time_s', 'Task_Success', 'Unintended_Stops_Starts',
        'Path_Deviations_Collisions', 'Stopping_Accuracy_cm', 'Turn_Accuracy_deg',
        'Qual_Turn_Fluidity_1to5', 'Qual_Axis_Utility_1to5', 'SUS_Score',
        'NASA_TLX_Mental', 'NASA_TLX_Physical', 'NASA_TLX_Temporal',
        'NASA_TLX_Performance', 'NASA_TLX_Effort', 'NASA_TLX_Frustration'
    ]
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(',', '.').astype(float)
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            print(f"Warnung: Spalte '{col}' nicht gefunden und übersprungen.")

    # --- 2. Quantitative Analyse ---
    participant_summary = df.groupby(['Participant_ID', 'Condition']).agg(
        Total_Task_Time_s=('Task_Completion_Time_s', 'sum'),
        Total_Unintended_Stops=('Unintended_Stops_Starts', 'sum'),
        Total_Path_Deviations=('Path_Deviations_Collisions', 'sum')
    ).reset_index()
    performance_summary = participant_summary.groupby('Condition').agg(
        Mean_Total_Task_Time_s=('Total_Task_Time_s', 'mean'),
        Std_Total_Task_Time_s=('Total_Task_Time_s', 'std'),
        Mean_Total_Unintended_Stops=('Total_Unintended_Stops', 'mean'),
        Std_Total_Unintended_Stops=('Total_Unintended_Stops', 'std'),
        Mean_Total_Path_Deviations=('Total_Path_Deviations', 'mean'),
        Std_Total_Path_Deviations=('Total_Path_Deviations', 'std')
    ).reset_index()

    accuracy_summary = df.groupby('Condition').agg(
        Mean_Stopping_Accuracy_cm=('Stopping_Accuracy_cm', 'mean'),
        Mean_Turn_Accuracy_deg=('Turn_Accuracy_deg', 'mean'),
        Mean_Turn_Fluidity_1to5=('Qual_Turn_Fluidity_1to5', 'mean'),
        Mean_Axis_Utility_1to5=('Qual_Axis_Utility_1to5', 'mean')
    ).reset_index()

    subjective_data = df.dropna(subset=['SUS_Score']).copy()
    tlx_cols = ['NASA_TLX_Mental', 'NASA_TLX_Physical', 'NASA_TLX_Temporal',
                'NASA_TLX_Performance', 'NASA_TLX_Effort', 'NASA_TLX_Frustration']
    subjective_data['NASA_TLX_Overall'] = subjective_data[tlx_cols].mean(axis=1)
    subjective_summary = subjective_data.groupby('Condition').agg(
        Mean_SUS_Score=('SUS_Score', 'mean'), Std_SUS_Score=('SUS_Score', 'std'),
        Mean_NASA_TLX_Overall=('NASA_TLX_Overall', 'mean'), Std_NASA_TLX_Overall=('NASA_TLX_Overall', 'std')
    ).reset_index()
    tlx_subscales_summary = subjective_data.groupby('Condition')[tlx_cols].mean().reset_index()

    # --- 3. Diagramme erstellen ---
    print("\nErstelle Diagramme...")

    sns.set_theme(style="whitegrid", palette="viridis")
    plt.rcParams['font.family'] = 'sans-serif';
    plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
    plt.rcParams['axes.titlesize'] = 16;
    plt.rcParams['axes.titleweight'] = 'bold'
    plt.rcParams['axes.labelsize'] = 12

    # Diagramm 1: SUS Score Vergleich (bleibt wie es war)
    plt.figure(figsize=(8, 6))
    sus_plot = sns.barplot(x=subjective_summary['Condition'], y=subjective_summary['Mean_SUS_Score'],
                           palette=['#4c72b0', '#55a868'], capsize=.1)
    plt.errorbar(x=subjective_summary['Condition'], y=subjective_summary['Mean_SUS_Score'],
                 yerr=subjective_summary['Std_SUS_Score'], fmt='none', c='black', capsize=5)
    sus_plot.set_title('System Usability Scale (SUS) Score Vergleich', fontsize=16)
    sus_plot.set_xlabel('Bedingung', fontsize=12);
    sus_plot.set_ylabel('Durchschnittlicher SUS Score (0-100)', fontsize=12)
    sus_plot.set_ylim(0, 100)
    for index, row in subjective_summary.iterrows():
        sus_plot.text(index, row.Mean_SUS_Score + 2, f'{row.Mean_SUS_Score:.1f}\n(±{row.Std_SUS_Score:.1f})',
                      color='black', ha="center", weight='bold')
    plt.tight_layout();
    plt.savefig('sus_comparison.png');
    plt.close()
    print("1. Diagramm 'sus_comparison.png' gespeichert.")

    # Diagramm 2: NASA-TLX Gesamt-Workload (bleibt wie es war)
    plt.figure(figsize=(8, 6))
    tlx_plot = sns.barplot(x=subjective_summary['Condition'], y=subjective_summary['Mean_NASA_TLX_Overall'],
                           palette=['#c44e52', '#8172b2'], capsize=.1)
    plt.errorbar(x=subjective_summary['Condition'], y=subjective_summary['Mean_NASA_TLX_Overall'],
                 yerr=subjective_summary['Std_NASA_TLX_Overall'], fmt='none', c='black', capsize=5)
    tlx_plot.set_title('NASA-TLX Gesamt-Arbeitslast (Workload) Vergleich', fontsize=16)
    tlx_plot.set_xlabel('Bedingung', fontsize=12);
    tlx_plot.set_ylabel('Durchschnittlicher Workload Score (1-20)', fontsize=12)
    tlx_plot.set_ylim(0, max(subjective_summary['Mean_NASA_TLX_Overall'].max(), 1) * 1.4)
    for index, row in subjective_summary.iterrows():
        tlx_plot.text(index, row.Mean_NASA_TLX_Overall + 0.3,
                      f'{row.Mean_NASA_TLX_Overall:.1f}\n(±{row.Std_NASA_TLX_Overall:.1f})', color='black', ha="center",
                      weight='bold')
    plt.tight_layout();
    plt.savefig('nasatlx_overall_comparison.png');
    plt.close()
    print("2. Diagramm 'nasatlx_overall_comparison.png' gespeichert.")

    # Diagramm 3: NASA-TLX Detaillierte Subskalen (bleibt wie es war)
    tlx_subscales_melted = tlx_subscales_summary.melt(id_vars='Condition', var_name='Subscale', value_name='Score')
    tlx_subscales_melted['Subscale'] = tlx_subscales_melted['Subscale'].str.replace('NASA_TLX_', '')
    plt.figure(figsize=(12, 7));
    subscale_plot = sns.barplot(data=tlx_subscales_melted, x='Subscale', y='Score', hue='Condition',
                                palette=['#4c72b0', '#55a868'])
    subscale_plot.set_title('Detaillierte NASA-TLX Workload Dimensionen', fontsize=16);
    subscale_plot.set_xlabel('Workload Dimension', fontsize=12);
    subscale_plot.set_ylabel('Durchschnittlicher Score (1-20)', fontsize=12)
    subscale_plot.set_xticklabels(subscale_plot.get_xticklabels(), rotation=15, ha='right');
    plt.legend(title='Bedingung', loc='upper left');
    plt.tight_layout();
    plt.savefig('nasatlx_subscales_comparison.png');
    plt.close()
    print("3. Diagramm 'nasatlx_subscales_comparison.png' gespeichert.")

    # --- BEGINN ÄNDERUNG: Ersetze altes "Diagramm 4" und füge ein neues hinzu ---

    # Diagramm 4 (vorher "Diagramm 4"): Performanz-Metriken als Diagramm
    performance_melted = performance_summary.melt(
        id_vars=['Condition'],
        value_vars=['Mean_Total_Task_Time_s', 'Mean_Total_Unintended_Stops', 'Mean_Total_Path_Deviations'],
        var_name='Metric', value_name='Value'
    )
    plt.figure(figsize=(12, 7));
    perf_plot = sns.barplot(data=performance_melted, x='Metric', y='Value', hue='Condition',
                            palette=['#4c72b0', '#55a868'])
    perf_plot.set_title('Durchschnittliche Performanz-Metriken pro Teilnehmer', fontsize=16);
    perf_plot.set_xlabel('Metrik', fontsize=12);
    perf_plot.set_ylabel('Durchschnittlicher Wert', fontsize=12)
    perf_plot.set_xticklabels(['Gesamtdauer (s)', 'Ungewollte Stopps', 'Pfadabweichungen'], ha='center');
    plt.legend(title='Bedingung');
    plt.tight_layout();
    plt.savefig('performance_metrics_chart.png');
    plt.close()
    print("4. Diagramm 'performance_metrics_chart.png' gespeichert.")

    # Diagramm 5 (NEU): Genauigkeits- & Rating-Metriken als Diagramm
    accuracy_melted = accuracy_summary.melt(
        id_vars=['Condition'],
        value_vars=['Mean_Stopping_Accuracy_cm', 'Mean_Turn_Accuracy_deg', 'Mean_Turn_Fluidity_1to5',
                    'Mean_Axis_Utility_1to5'],
        var_name='Metric', value_name='Value'
    )
    plt.figure(figsize=(14, 7));  # Etwas breiter für mehr Labels
    acc_plot = sns.barplot(data=accuracy_melted, x='Metric', y='Value', hue='Condition', palette=['#4c72b0', '#55a868'])
    acc_plot.set_title('Durchschnittliche Genauigkeits- & Rating-Metriken', fontsize=16);
    acc_plot.set_xlabel('Metrik', fontsize=12);
    acc_plot.set_ylabel('Durchschnittlicher Wert', fontsize=12)
    acc_plot.set_xticklabels(
        ['Stopp-Genauigkeit (cm)', 'Dreh-Genauigkeit (Grad)', 'Dreh-Flüssigkeit (1-5)', 'Achsen-Nützlichkeit (1-5)'],
        rotation=10, ha='right');
    plt.legend(title='Bedingung');
    plt.tight_layout();
    plt.savefig('accuracy_ratings_chart.png');
    plt.close()
    print("5. Diagramm 'accuracy_ratings_chart.png' gespeichert.")

    # --- ENDE ÄNDERUNG ---

    # --- 5. Textliche Ausgabe der Ergebnisse ---
    # ... (bleibt wie es war) ...
    print("\n\n--- Detaillierte Auswertung der Nutzertest-Daten ---\n")
    print("Hinweis: Die Auswertung basiert auf den verfügbaren Daten.\n")

    print("\n--- Quantitative Auswertung ---")
    print("\n**1. Performanz-Metriken (Durchschnittliche Summen pro Teilnehmer je Bedingung):**")
    print(performance_summary.round(2).to_string())
    print("\n**2. Genauigkeits- & Rating-Metriken (Mittelwerte pro Bedingung):**")
    print(accuracy_summary.round(2).to_string())
    print("\n**3. Subjektive Fragebögen (Mittelwerte pro Bedingung):**")
    print(subjective_summary.round(2).to_string())
    print("\n**4. Detaillierte NASA-TLX Subskalen (Mittelwerte pro Bedingung):**")
    print(tlx_subscales_summary.to_string())

    # --- 6. Qualitative Analyse ---
    print("\n\n--- Zusammenfassung der qualitativen Beobachtungen ---")
    qualitative_notes = df[['Participant_ID', 'Condition', 'Observer_Notes', 'Participant_Comments']].dropna(how='all')
    if not qualitative_notes.empty:
        for index, row in qualitative_notes.iterrows():
            if pd.notna(row['Observer_Notes']) and row['Observer_Notes'].strip():
                print(f"- [Beobachtung] {row['Participant_ID']} ({row['Condition']}): {row['Observer_Notes']}")
            if pd.notna(row['Participant_Comments']) and row['Participant_Comments'].strip():
                print(f"- [Kommentar] {row['Participant_ID']} ({row['Condition']}): {row['Participant_Comments']}")
    else:
        print("Keine qualitativen Notizen oder Kommentare in der Datei gefunden.")


# Führe die Analysefunktion aus, wenn das Skript direkt gestartet wird
if __name__ == "__main__":
    analyze_test_data()