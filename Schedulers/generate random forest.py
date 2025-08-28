import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

# Step 1: Load the dataset
data = pd.read_csv('../relaxation_training_data.csv')

# Step 2: Prepare features (X) and labels (y)
# Features: taskset_id, time, remaining_time, deadline, priority, laxity
# Label: core_id (which core the scheduler chose)

feature_columns = ['taskset_id', 'time', 'remaining_time', 'deadline', 'priority', 'laxity']
X = data[feature_columns]
y = data['core_id']

# Step 3: Train/test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Step 4: Train Random Forest
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Step 5: Evaluate the model
y_pred = model.predict(X_test)

print("\n🎯 Accuracy Score:", accuracy_score(y_test, y_pred))
print("\n📋 Classification Report:\n", classification_report(y_test, y_pred))
print("\n🔎 Confusion Matrix:\n", confusion_matrix(y_test, y_pred))

# Step 6: Save the model if needed
import joblib
joblib.dump(model, '../relaxation_rf_model.pkl')

print("\n✅ Model saved as 'relaxation_rf_model.pkl'")
