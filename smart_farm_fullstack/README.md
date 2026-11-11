# Smart Farm — Full-stack application with AI screening and agronomy references

Developed by **Fares Hazem & Mostafa El-Shennawy**

## Included
- Bilingual English/Arabic Flask website and 16×16 farm map.
- SQLite backend, authenticated ESP32 sensor endpoint, farmer phone image uploads.
- Real local Hugging Face plant-leaf image classifier (38 crop-condition classes).
- FAO crop salinity thresholds and method-aware salinity screening.
- Sensor measurement and calibration guidance.

## Run locally (Windows)
1. Install Python 3.10+.
2. `py -m venv venv`
3. `venv\Scripts\activate`
4. `pip install -r requirements.txt`
5. `pip install -r requirements-ai.txt`
6. Copy `.env.example` to `.env`, set strong random `FLASK_SECRET` and `ROBOT_API_KEY`.
7. `python -m flask --app app run --host 0.0.0.0 --port 5000`
8. Open `http://127.0.0.1:5000`.

The first AI image request downloads model weights from Hugging Face. This needs internet access on the server and adequate RAM/CPU; the first inference may be slow.

## AI model and scientific limits
Model: `rodynaemad/plant-disease-dinov2-small` from Hugging Face, loaded locally with Transformers.
- 38 crop-condition classes: 26 disease classes and 12 healthy classes across 14 crops.
- Model card reports 98.9% accuracy / 98.5% macro F1 on a held-out, leaf-grouped PlantVillage test set. These are author-reported benchmark results, not Smart Farm's own validation and not expected field accuracy.
- Model card warns that field photos with clutter, shadows, multiple leaves and varying cameras perform substantially worse. It is closed-set and may force an unknown crop/disease into one of the 38 known classes.
- Smart Farm returns top-3 candidates, a confidence score and an uncertainty state. Softmax confidence is not the probability that a field diagnosis is correct.
- One clear leaf photo is the intended input. Other crops, nutrient deficiencies, abiotic stress, mixed infections and pests outside the model classes are out of scope.
- Do not use the result alone to apply pesticides/fertilizers. Confirm with an Egyptian agronomist/plant clinic and use only locally registered products and label directions.
- License: CC BY-SA 4.0 for this fine-tuned model. Preserve attribution/license notices if redistributing model weights or derivatives.

Model card: https://huggingface.co/rodynaemad/plant-disease-dinov2-small

## Crop salinity reference included
FAO Irrigation and Drainage Paper 29, Annex 1 lists crop salt tolerance thresholds (a) and yield decline slopes (b) for ECe:
`relative yield (%) = 100 - b × (ECe - a)` when ECe exceeds the threshold; otherwise 100%.
The app includes a selected subset of the FAO crop table. Values are general guidelines and depend on cultivar, climate, soil conditions, crop stage and management.

**Critical method safeguard:** ECe is electrical conductivity of a saturated-paste extract from root-zone soil, reported in dS/m at 25°C. The website ranks crops by this table only if the reading metadata explicitly says `ec_method: "ECe"` and `ec_unit: "dS/m"`. Do NOT label a direct-insertion soil probe, a 1:1 or 1:2 soil-water extract, irrigation-water ECw, or TDS reading as ECe. For these methods the site withholds crop ranking.

References:
- FAO, Annex 1. Crop salt tolerance data: https://www.fao.org/4/y4263e/y4263e0e.htm
- FAO, Water quality for agriculture: https://www.fao.org/4/t0234e/T0234E03.htm

## Sensor measurement and QA guidance
- Soil pH/EC values depend on sample preparation and soil:water ratio. Texas A&M Soil Testing Lab documents pH and EC measurement on a 1:2 soil:water extract, stirred and equilibrated for at least 30 minutes. These values are not interchangeable with ECe or other extract ratios.
- USDA NRCS Soil Quality Test Kit Guide describes a 1:1 soil:water EC test and says to calibrate the EC meter. This is a different method from ECe.
- USDA NRCS Soil Survey Field and Laboratory Methods explains temperature effects on EC and methods for aqueous extracts.
- pH meters should be calibrated with certified buffer solutions that bracket the expected range (commonly pH 4, 7 and 10), and checked with a reference soil. Record date, buffers, slope/offset if available and reference result.
- Soil moisture probes infer water content from an electrical response; calibration depends on soil texture, salinity, temperature, probe contact and sensor model. Do not treat a raw ADC count or generic percent as universal volumetric water content.
- The API stores sensor model, calibration date and measurement depth metadata with each reading. Add serial number, raw ADC/voltage and calibration reference values to the schema/firmware when the final sensor models are selected.
- pH inputs are range-checked (0–14), moisture/battery (0–100), EC non-negative and soil temperature (-20 to 80°C). These are basic input sanity checks, not proof of sensor accuracy.
- Validate against laboratory/reference measurements before making research claims.
- EC, pH, moisture and ordinary RGB photos do not identify N, P and K individually. Use validated nutrient extraction/lab methods or a properly validated test kit.

References:
- Texas A&M AgriLife Soil Testing Lab Methods: https://soiltesting.tamu.edu/laboratory-methods/
- USDA NRCS Soil Quality Test Kit Guide: https://www.nrcs.usda.gov/sites/default/files/2022-10/Soil%20Quality%20Test%20Kit%20Guide.pdf
- USDA NRCS Soil Survey Field and Laboratory Methods: https://www.nrcs.usda.gov/sites/default/files/2023-01/SSIR51.pdf
- USGS, In situ soil moisture sensors in undisturbed soils: https://www.usgs.gov/publications/situ-soil-moisture-sensors-undisturbed-soils

## ESP32 endpoint
`POST /api/robot/readings`
Headers: `Content-Type: application/json`, `X-API-Key: <ROBOT_API_KEY>`
Example:
```json
{
  "robot_id":"smartfarm-01",
  "zone_id":"A1",
  "moisture":42.5,
  "soil_temp":23.8,
  "ph":6.7,
  "ec":1.2,
  "ec_method":"ECe",
  "ec_unit":"dS/m",
  "battery":87,
  "sensor_model":"sensor model and part number",
  "calibration_date":"2026-11-10",
  "measurement_depth_cm":10
}
```
Only send ECe metadata if the EC measurement genuinely comes from the saturated-paste method at 25°C. Use null for unavailable readings.

## Production requirements still needed
This is runnable application code, not a deployed public website. Public launch still requires hosting, HTTPS, environment secrets, user authentication, backups, persistent file storage, a production database, field validation on Egyptian crops/conditions and a documented sensor calibration study. Never expose the robot API key in browser JavaScript.
