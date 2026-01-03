BaseURL (local): http://127.0.0.1:8000

Route: "/verify"
Method: POST

## Payload Example:
```json
{
  "startUrl": "https://verified.capitalone.com/",
  "steps": [
    {
      "waitUrlContains": "auth/signin",
      "actions": [
        { "kind": "click", "selector": "button[data-testtarget=\"linkToForgots\"]" }
      ]
    },
    {
      "waitUrlContains": "sign-in-help/pii?client=SIC",
      "actions": [
        { "kind": "typeSlow", "selector": "#lastname", "value": "Smith" },
        { "kind": "typeSlow", "selector": "#dob", "value": "01/01/1990" },
        { "kind": "click", "selector": "#fullSSN" },
        { "kind": "cdpType", "value": "000000000" },
        { "kind": "click", "selector": "button[data-testtarget=\"pii-form-submit-btn\"]" }
      ]
    }
  ]
}
```

# VIEW MORE ROUTES AVIALABLE AT: __http://127.0.0.1:8000/docs__ (GET)
