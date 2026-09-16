from orchestrator import run_diagnosis_from_text

text = "I feel chest pressure and breathing difficulty when walking upstairs"

result = run_diagnosis_from_text(text)

print("Diagnosis Result")
print(result)