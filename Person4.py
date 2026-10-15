#IMport FAstAPI Framework
#FAstAPI helps create APU endpoints quickly
from fastapi import FastAPI

#APi Application
app= FastAPI(
    title="AgriTrial API"
)
@app.get ("/")
def home():
    #Return a JSON response
    return {
        "message": "AgriTrial API is running"
    }

#GEt trial ENDPOINT
@app.get("/trials")
def get_trials():
    trials = [
        {
            "site_id": 1,
            "crop": "Maize",
            "week": 1
        },
        {
            "site_id": 1,
            "crop": "Wheat",
            "week": 2
        }
    ]
    return trials
