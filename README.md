# zwift_ride_keytrigger

## Pre Requisite

Works only with Zwift Ride. Zwift Play / Click have encryption, should be easy to extend but I don't have those devices to test. 

It works in Windows or MacOS. 

Download python3. Recommended from [Microsoft Store](https://apps.microsoft.com/detail/9NCVDN91XZQP?hl=en-us&gl=CZ&ocid=pdpshare), but there are multiple options (brew, etc)

## Installation

Download / Clone the github repo.
Navigate to the folder.
```bash
pip install -r requirements.txt
# Try pip3 if pip gives an error
```

## Usage

Adjust keymapping.json as required (should be working for MyWhoosh)

```bash
python app.py
# Try python3 if pip gives an error
```
Whenever you press a key on the zwift ride, it should make the mapped keypress across all the system.

## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.
