# Cluster Job Runner


### Pre-Requisites
- Python 3.13+ installed
- git version 2.47+ installed
- minkube cluster running locally

## Quickstart

#### Step 1: Clone the repository.
```
git clone https://github.com/parth-dhiman/shakudo-cluster-job-runner

cd shakudo-cluster-job-runner
```

#### Step 2: Set up a virtual environment.
```
python -m venv venv
```

#### Step 3: Activate the virtual environment.
```
# If you're on Linux/macOS, run:
source venv/bin/activate    

# If you're on Windows, run:
./venv/Scripts/Activate.ps1
```

### Step 4: Install the required dependencies.
```
pip install -r requirements.txt
```

### Step 5: Run the app.
```
python run.py
```

## API Endpoints

The following endpoints have been implemented.

| Method | Path | Behavior |
| -------- | -------- | -------- |
| POST | /api/jobs | Create a Job from a JSON spec. Create the namespace if it does not exist. Return the created Jobʼs UID and initial status. |

## More sections to be written... 
