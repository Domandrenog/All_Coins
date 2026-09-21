# API Reference

**Base URL:** `https://track-coin-collection.base44.app/api`

## Setup

```bash
npm install @base44/sdk
```

```javascript
import { createClient } from '@base44/sdk';

const base44 = createClient({
  appId: "69f12d4bf0bb6ef2f9eaa84e",
  headers: {
    "Authorization": "Bearer YOUR_PERSONAL_ACCESS_TOKEN"
  }
});
```

## CoinVariant

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `coin_id` | string | Yes |  |
| `tag` | string | Yes |  |
| `condition` | `Tenho`, `Má Qualidade`, `Não Tenho` | Yes |  |
| `ordem` | integer |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/CoinVariant`
List CoinVariant records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.CoinVariant.list();
```

### `POST /entities/CoinVariant`
Create a CoinVariant record

```javascript
const record = await base44.entities.CoinVariant.create({
  // your data
});
```

### `DELETE /entities/CoinVariant`
Delete multiple CoinVariant records

```javascript
await base44.entities.CoinVariant.deleteMany({
  // query filter — WARNING: empty {} deletes ALL records
  coin_id: "Example coin_id"
});
```

### `POST /entities/CoinVariant/bulk`
Bulk create CoinVariant records

```javascript
const records = await base44.entities.CoinVariant.bulkCreate([
  { /* record 1 */ },
  { /* record 2 */ },
]);
```

### `PUT /entities/CoinVariant/bulk`
Bulk update CoinVariant records

```javascript
// bulk-update is not available via SDK — use the REST API
```

### `PATCH /entities/CoinVariant/update-many`
Update many CoinVariant records by query

```javascript
// update-many is not available via SDK — use the REST API
```

### `GET /entities/CoinVariant/{CoinVariant_id}`
Get a CoinVariant record by ID

**Parameters:**
- `CoinVariant_id` (path): Record ID

```javascript
const record = await base44.entities.CoinVariant.get(recordId);
```

### `PUT /entities/CoinVariant/{CoinVariant_id}`
Update a CoinVariant record

**Parameters:**
- `CoinVariant_id` (path): Record ID

```javascript
const record = await base44.entities.CoinVariant.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/CoinVariant/{CoinVariant_id}`
Delete a CoinVariant record

**Parameters:**
- `CoinVariant_id` (path): Record ID

```javascript
await base44.entities.CoinVariant.delete(recordId);
```

### `PUT /entities/CoinVariant/{CoinVariant_id}/restore`
Restore a deleted CoinVariant record

**Parameters:**
- `CoinVariant_id` (path): Record ID

```javascript
const record = await base44.entities.CoinVariant.restore(recordId);
```

## SpecialCoin

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `country` | string | Yes |  |
| `continent` | `Europa`, `América`, `Ásia`, `África`, `Oceânia` | Yes |  |
| `name` | string | Yes |  |
| `commemorative_name` | string |  |  |
| `year` | string |  |  |
| `condition` | `Tenho`, `Má Qualidade`, `Por Entregar`, `Não Tenho` | Yes |  |
| `image_frente` | string |  |  |
| `image_verso` | string |  |  |
| `adquirida_por` | string |  |  |
| `data_aquisicao` | string |  |  |
| `local_compra` | string |  |  |
| `valor_pago` | number |  |  |
| `moeda_valor` | string |  |  |
| `notes` | string |  |  |
| `url_numista` | string |  |  |
| `url_ucoin` | string |  |  |
| `ordem` | integer |  |  |
| `hidden` | boolean |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/SpecialCoin`
List SpecialCoin records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.SpecialCoin.list();
```

### `POST /entities/SpecialCoin`
Create a SpecialCoin record

```javascript
const record = await base44.entities.SpecialCoin.create({
  // your data
});
```

### `DELETE /entities/SpecialCoin`
Delete multiple SpecialCoin records

```javascript
await base44.entities.SpecialCoin.deleteMany({
  // query filter — WARNING: empty {} deletes ALL records
  country: "Example country"
});
```

### `POST /entities/SpecialCoin/bulk`
Bulk create SpecialCoin records

```javascript
const records = await base44.entities.SpecialCoin.bulkCreate([
  { /* record 1 */ },
  { /* record 2 */ },
]);
```

### `PUT /entities/SpecialCoin/bulk`
Bulk update SpecialCoin records

```javascript
// bulk-update is not available via SDK — use the REST API
```

### `PATCH /entities/SpecialCoin/update-many`
Update many SpecialCoin records by query

```javascript
// update-many is not available via SDK — use the REST API
```

### `GET /entities/SpecialCoin/{SpecialCoin_id}`
Get a SpecialCoin record by ID

**Parameters:**
- `SpecialCoin_id` (path): Record ID

```javascript
const record = await base44.entities.SpecialCoin.get(recordId);
```

### `PUT /entities/SpecialCoin/{SpecialCoin_id}`
Update a SpecialCoin record

**Parameters:**
- `SpecialCoin_id` (path): Record ID

```javascript
const record = await base44.entities.SpecialCoin.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/SpecialCoin/{SpecialCoin_id}`
Delete a SpecialCoin record

**Parameters:**
- `SpecialCoin_id` (path): Record ID

```javascript
await base44.entities.SpecialCoin.delete(recordId);
```

### `PUT /entities/SpecialCoin/{SpecialCoin_id}/restore`
Restore a deleted SpecialCoin record

**Parameters:**
- `SpecialCoin_id` (path): Record ID

```javascript
const record = await base44.entities.SpecialCoin.restore(recordId);
```

## CountryNote

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `country` | string | Yes |  |
| `continent` | `Europa`, `América`, `Ásia`, `África`, `Oceânia` | Yes |  |
| `name` | string | Yes |  |
| `year` | string |  |  |
| `condition` | `Tenho`, `Dobrada`, `Má Qualidade`, `Por Entregar`, `Não Tenho` | Yes |  |
| `image_frente` | string |  |  |
| `image_verso` | string |  |  |
| `adquirida_por` | string |  |  |
| `data_aquisicao` | string |  |  |
| `valor_facial` | string |  |  |
| `moeda_valor` | string |  |  |
| `url_numista` | string |  |  |
| `url_ucoin` | string |  |  |
| `notes` | string |  |  |
| `ordem` | integer |  |  |
| `hidden` | boolean |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/CountryNote`
List CountryNote records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.CountryNote.list();
```

### `POST /entities/CountryNote`
Create a CountryNote record

```javascript
const record = await base44.entities.CountryNote.create({
  // your data
});
```

### `DELETE /entities/CountryNote`
Delete multiple CountryNote records

```javascript
await base44.entities.CountryNote.deleteMany({
  // query filter — WARNING: empty {} deletes ALL records
  country: "Example country"
});
```

### `POST /entities/CountryNote/bulk`
Bulk create CountryNote records

```javascript
const records = await base44.entities.CountryNote.bulkCreate([
  { /* record 1 */ },
  { /* record 2 */ },
]);
```

### `PUT /entities/CountryNote/bulk`
Bulk update CountryNote records

```javascript
// bulk-update is not available via SDK — use the REST API
```

### `PATCH /entities/CountryNote/update-many`
Update many CountryNote records by query

```javascript
// update-many is not available via SDK — use the REST API
```

### `GET /entities/CountryNote/{CountryNote_id}`
Get a CountryNote record by ID

**Parameters:**
- `CountryNote_id` (path): Record ID

```javascript
const record = await base44.entities.CountryNote.get(recordId);
```

### `PUT /entities/CountryNote/{CountryNote_id}`
Update a CountryNote record

**Parameters:**
- `CountryNote_id` (path): Record ID

```javascript
const record = await base44.entities.CountryNote.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/CountryNote/{CountryNote_id}`
Delete a CountryNote record

**Parameters:**
- `CountryNote_id` (path): Record ID

```javascript
await base44.entities.CountryNote.delete(recordId);
```

### `PUT /entities/CountryNote/{CountryNote_id}/restore`
Restore a deleted CountryNote record

**Parameters:**
- `CountryNote_id` (path): Record ID

```javascript
const record = await base44.entities.CountryNote.restore(recordId);
```

## CountrySettings

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `country` | string | Yes |  |
| `features` | object |  |  |
| `defaults` | object |  |  |
| `completeness` | object |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/CountrySettings`
List CountrySettings records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.CountrySettings.list();
```

### `POST /entities/CountrySettings`
Create a CountrySettings record

```javascript
const record = await base44.entities.CountrySettings.create({
  // your data
});
```

### `DELETE /entities/CountrySettings`
Delete multiple CountrySettings records

```javascript
await base44.entities.CountrySettings.deleteMany({
  // query filter — WARNING: empty {} deletes ALL records
  country: "Example country"
});
```

### `POST /entities/CountrySettings/bulk`
Bulk create CountrySettings records

```javascript
const records = await base44.entities.CountrySettings.bulkCreate([
  { /* record 1 */ },
  { /* record 2 */ },
]);
```

### `PUT /entities/CountrySettings/bulk`
Bulk update CountrySettings records

```javascript
// bulk-update is not available via SDK — use the REST API
```

### `PATCH /entities/CountrySettings/update-many`
Update many CountrySettings records by query

```javascript
// update-many is not available via SDK — use the REST API
```

### `GET /entities/CountrySettings/{CountrySettings_id}`
Get a CountrySettings record by ID

**Parameters:**
- `CountrySettings_id` (path): Record ID

```javascript
const record = await base44.entities.CountrySettings.get(recordId);
```

### `PUT /entities/CountrySettings/{CountrySettings_id}`
Update a CountrySettings record

**Parameters:**
- `CountrySettings_id` (path): Record ID

```javascript
const record = await base44.entities.CountrySettings.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/CountrySettings/{CountrySettings_id}`
Delete a CountrySettings record

**Parameters:**
- `CountrySettings_id` (path): Record ID

```javascript
await base44.entities.CountrySettings.delete(recordId);
```

### `PUT /entities/CountrySettings/{CountrySettings_id}/restore`
Restore a deleted CountrySettings record

**Parameters:**
- `CountrySettings_id` (path): Record ID

```javascript
const record = await base44.entities.CountrySettings.restore(recordId);
```

## Coin

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes |  |
| `country` | string | Yes |  |
| `continent` | `Europa`, `América`, `Ásia`, `África`, `Oceânia` | Yes |  |
| `years` | string |  |  |
| `condition` | `Tenho`, `Má Qualidade`, `Por Entregar`, `Não Tenho` | Yes |  |
| `rarity` | `Circulante`, `Escassa`, `Retirada`, `Histórica` |  |  |
| `has_variants` | boolean |  |  |
| `image_frente` | string |  |  |
| `image_verso` | string |  |  |
| `adquirida_por` | string |  |  |
| `data_aquisicao` | string |  |  |
| `url_numista` | string |  |  |
| `url_ucoin` | string |  |  |
| `local_compra` | string |  |  |
| `valor_pago` | number |  |  |
| `moeda_valor` | string |  |  |
| `notes` | string |  |  |
| `ordem` | integer |  |  |
| `hidden` | boolean |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/Coin`
List Coin records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.Coin.list();
```

### `POST /entities/Coin`
Create a Coin record

```javascript
const record = await base44.entities.Coin.create({
  // your data
});
```

### `DELETE /entities/Coin`
Delete multiple Coin records

```javascript
await base44.entities.Coin.deleteMany({
  // query filter — WARNING: empty {} deletes ALL records
  name: "Example name"
});
```

### `POST /entities/Coin/bulk`
Bulk create Coin records

```javascript
const records = await base44.entities.Coin.bulkCreate([
  { /* record 1 */ },
  { /* record 2 */ },
]);
```

### `PUT /entities/Coin/bulk`
Bulk update Coin records

```javascript
// bulk-update is not available via SDK — use the REST API
```

### `PATCH /entities/Coin/update-many`
Update many Coin records by query

```javascript
// update-many is not available via SDK — use the REST API
```

### `GET /entities/Coin/{Coin_id}`
Get a Coin record by ID

**Parameters:**
- `Coin_id` (path): Record ID

```javascript
const record = await base44.entities.Coin.get(recordId);
```

### `PUT /entities/Coin/{Coin_id}`
Update a Coin record

**Parameters:**
- `Coin_id` (path): Record ID

```javascript
const record = await base44.entities.Coin.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/Coin/{Coin_id}`
Delete a Coin record

**Parameters:**
- `Coin_id` (path): Record ID

```javascript
await base44.entities.Coin.delete(recordId);
```

### `PUT /entities/Coin/{Coin_id}/restore`
Restore a deleted Coin record

**Parameters:**
- `Coin_id` (path): Record ID

```javascript
const record = await base44.entities.Coin.restore(recordId);
```

## CoinSighting

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `coin_id` | string | Yes |  |
| `item_type` | `normal_coin`, `special_coin`, `country_note` |  |  |
| `item_id` | string |  |  |
| `coin_name` | string | Yes |  |
| `country` | string |  |  |
| `continent` | string |  |  |
| `years` | string |  |  |
| `username` | string | Yes |  |
| `user_email` | string | Yes |  |
| `status` | `por_entregar`, `a_sincronizar`, `entregue`, `cancelado`, `revisao_manual` | Yes |  |
| `quality` | `Boa Qualidade`, `Má Qualidade` |  |  |
| `variant_tag` | string |  |  |
| `notes` | string |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/CoinSighting`
List CoinSighting records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.CoinSighting.list();
```

### `POST /entities/CoinSighting`
Create a CoinSighting record

```javascript
const record = await base44.entities.CoinSighting.create({
  // your data
});
```

### `DELETE /entities/CoinSighting`
Delete multiple CoinSighting records

```javascript
await base44.entities.CoinSighting.deleteMany({
  // query filter — WARNING: empty {} deletes ALL records
  coin_id: "Example coin_id"
});
```

### `POST /entities/CoinSighting/bulk`
Bulk create CoinSighting records

```javascript
const records = await base44.entities.CoinSighting.bulkCreate([
  { /* record 1 */ },
  { /* record 2 */ },
]);
```

### `PUT /entities/CoinSighting/bulk`
Bulk update CoinSighting records

```javascript
// bulk-update is not available via SDK — use the REST API
```

### `PATCH /entities/CoinSighting/update-many`
Update many CoinSighting records by query

```javascript
// update-many is not available via SDK — use the REST API
```

### `GET /entities/CoinSighting/{CoinSighting_id}`
Get a CoinSighting record by ID

**Parameters:**
- `CoinSighting_id` (path): Record ID

```javascript
const record = await base44.entities.CoinSighting.get(recordId);
```

### `PUT /entities/CoinSighting/{CoinSighting_id}`
Update a CoinSighting record

**Parameters:**
- `CoinSighting_id` (path): Record ID

```javascript
const record = await base44.entities.CoinSighting.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/CoinSighting/{CoinSighting_id}`
Delete a CoinSighting record

**Parameters:**
- `CoinSighting_id` (path): Record ID

```javascript
await base44.entities.CoinSighting.delete(recordId);
```

### `PUT /entities/CoinSighting/{CoinSighting_id}/restore`
Restore a deleted CoinSighting record

**Parameters:**
- `CoinSighting_id` (path): Record ID

```javascript
const record = await base44.entities.CoinSighting.restore(recordId);
```

## Souvenir

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes |  |
| `continent` | `Europa`, `América`, `Ásia`, `África`, `Oceânia` | Yes |  |
| `country` | string | Yes |  |
| `city` | string | Yes |  |
| `type` | `pressed`, `coin`, `card`, `other` | Yes |  |
| `condition` | `Tenho`, `Não Tenho` | Yes |  |
| `location_name` | string |  |  |
| `description` | string |  |  |
| `display_shape` | `oval`, `circle`, `card_wide`, `square` |  |  |
| `image_front` | string |  |  |
| `image_back` | string |  |  |
| `acquisition_date` | string |  |  |
| `notes` | string |  |  |
| `reference_url` | string |  |  |
| `ordem` | integer |  |  |
| `hidden` | boolean |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/Souvenir`
List Souvenir records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.Souvenir.list();
```

### `POST /entities/Souvenir`
Create a Souvenir record

```javascript
const record = await base44.entities.Souvenir.create({
  // your data
});
```

### `DELETE /entities/Souvenir`
Delete multiple Souvenir records

```javascript
await base44.entities.Souvenir.deleteMany({
  // query filter — WARNING: empty {} deletes ALL records
  name: "Example name"
});
```

### `POST /entities/Souvenir/bulk`
Bulk create Souvenir records

```javascript
const records = await base44.entities.Souvenir.bulkCreate([
  { /* record 1 */ },
  { /* record 2 */ },
]);
```

### `PUT /entities/Souvenir/bulk`
Bulk update Souvenir records

```javascript
// bulk-update is not available via SDK — use the REST API
```

### `PATCH /entities/Souvenir/update-many`
Update many Souvenir records by query

```javascript
// update-many is not available via SDK — use the REST API
```

### `GET /entities/Souvenir/{Souvenir_id}`
Get a Souvenir record by ID

**Parameters:**
- `Souvenir_id` (path): Record ID

```javascript
const record = await base44.entities.Souvenir.get(recordId);
```

### `PUT /entities/Souvenir/{Souvenir_id}`
Update a Souvenir record

**Parameters:**
- `Souvenir_id` (path): Record ID

```javascript
const record = await base44.entities.Souvenir.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/Souvenir/{Souvenir_id}`
Delete a Souvenir record

**Parameters:**
- `Souvenir_id` (path): Record ID

```javascript
await base44.entities.Souvenir.delete(recordId);
```

### `PUT /entities/Souvenir/{Souvenir_id}/restore`
Restore a deleted Souvenir record

**Parameters:**
- `Souvenir_id` (path): Record ID

```javascript
const record = await base44.entities.Souvenir.restore(recordId);
```

## User

### Schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `email` | string | Yes | The email of the user |
| `full_name` | string | Yes | The full name of the user |
| `role` | `admin`, `user` |  |  |
| `username` | string | Yes |  |
| `nationality` | string | Yes |  |
| `view_mode` | `all`, `circulante` |  |  |
| `language` | `pt`, `en` | Yes |  |
| `onboarding_complete` | boolean |  |  |
| `id` | string |  | Unique record identifier |
| `created_date` | string |  | Record creation timestamp |
| `updated_date` | string |  | Record last update timestamp |
| `created_by_id` | string |  | ID of the user who created the record |

### Endpoints

### `GET /entities/User`
List User records

**Parameters:**
- `q` (query): JSON query filter, e.g. {"status":"active"}
- `limit` (query): Maximum number of records to return
- `skip` (query): Number of records to skip (pagination)
- `sort_by` (query): Field name to sort by. Prefix with '-' for descending order, e.g. -created_date

```javascript
const records = await base44.entities.User.list();
```

### `POST /entities/User`
Create a User record

```javascript
const record = await base44.entities.User.create({
  // your data
});
```

### `GET /entities/User/{User_id}`
Get a User record by ID

**Parameters:**
- `User_id` (path): Record ID

```javascript
const record = await base44.entities.User.get(recordId);
```

### `PUT /entities/User/{User_id}`
Update a User record

**Parameters:**
- `User_id` (path): Record ID

```javascript
const record = await base44.entities.User.update(recordId, {
  // fields to update
});
```

### `DELETE /entities/User/{User_id}`
Delete a User record

**Parameters:**
- `User_id` (path): Record ID

```javascript
await base44.entities.User.delete(recordId);
```
