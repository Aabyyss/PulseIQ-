import pandas as pd
import matplotlib.pyplot as plt

data = pd.read_csv("data/heart.csv")

print(data.head())

plt.hist(data["age"])
plt.title("Age Distribution")
plt.xlabel("Age")
plt.ylabel("Patients")

plt.show()