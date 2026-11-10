package bb.edu.cimh.sia.data

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.serializer
import okhttp3.OkHttpClient

/** docs/api/inventory.openapi.yaml: the parts SIA Mobile uses. Unknown fields are ignored. */
@Serializable
data class Shelf(
    val barcode: String,
    val number: Int,
    val site: String,
    val location: String,
    val siteName: String? = null,
    val locationName: String? = null,
) {
    val label: String get() = listOfNotNull(siteName ?: site, locationName ?: location, "Shelf $number").joinToString(" · ")
}

@Serializable
data class StockUnit(
    val barcode: String,
    val product: String,
    val productName: String? = null,
    val serial: String? = null,
    val siteName: String? = null,
    val locationName: String? = null,
    val shelf: String? = null,
    val shelfNumber: Int? = null,
    val stowed: Boolean = false,
    val picked: Boolean = false,
    val pickedReason: String? = null,
    val orderId: String? = null,
    val reservedFor: String? = null,
    val assignedTo: String? = null,
) {
    val place: String?
        get() = if (shelf == null) null else listOfNotNull(siteName, locationName, shelfNumber?.let { "Shelf $it" }).joinToString(" · ")
}

@Serializable
data class UnitPage(val items: List<StockUnit>, val nextCursor: String? = null)

@Serializable
data class StockPlace(
    val shelf: String,
    val count: Int,
    val siteName: String? = null,
    val locationName: String? = null,
    val shelfNumber: Int? = null,
) {
    val label: String get() = listOfNotNull(siteName, locationName, shelfNumber?.let { "Shelf $it" }).joinToString(" · ")
}

@Serializable
data class ProductStock(
    val productId: String,
    val productName: String? = null,
    val available: Int,
    val reserved: Int,
    val picked: Int,
    val assigned: Int = 0,
    val threshold: Int = 0,
    val byLocation: List<StockPlace> = emptyList(),
)

@Serializable
data class StowBody(val unit: String, val shelf: String)

@Serializable
data class PickBody(val unit: String, val reason: String? = null, val orderId: String? = null)

@Serializable
data class RelocateBody(val unit: String, val toShelf: String)

@Serializable
data class AssignBody(val unit: String, val accountId: String)

@Serializable
data class UnassignBody(val unit: String)

@Serializable
data class Site(val barcode: String, val name: String, val country: String, val active: Boolean = true)

@Serializable
data class SiteInput(val name: String, val country: String, val address: String? = null)

@Serializable
data class Location(
    val barcode: String,
    val name: String,
    val site: String,
    val active: Boolean = true,
    val shelfCount: Int? = null,
)

@Serializable
data class LocationInput(val name: String, val description: String? = null)

@Serializable
data class ShelvesInput(val count: Int)

@Serializable
data class Items<T>(val items: List<T>)

class InventoryApi(baseUrl: String, client: OkHttpClient) {
    private val api = ApiClient(baseUrl, "inventory", client)

    // M-10: places (site → location → shelves). Online only: new codes come from the server.
    suspend fun sites(): List<Site> = api.get(api.url("sites"), Items.serializer(Site.serializer())).items

    suspend fun createSite(input: SiteInput): Site = api.post(api.url("sites"), input, serializer(), serializer())

    suspend fun locations(site: String): List<Location> =
        api.get(api.url(listOf("sites", site, "locations")), Items.serializer(Location.serializer())).items

    suspend fun createLocation(site: String, input: LocationInput): Location =
        api.post(api.url(listOf("sites", site, "locations")), input, serializer(), serializer())

    suspend fun addShelves(location: String, count: Int): List<Shelf> =
        api.post(api.url(listOf("locations", location, "shelves")), ShelvesInput(count), serializer(), Items.serializer(Shelf.serializer())).items

    suspend fun shelf(barcode: String): Shelf = api.get(api.url(listOf("shelves", barcode)), serializer())

    suspend fun shelfUnits(barcode: String, cursor: String? = null): UnitPage =
        api.get(api.url(listOf("shelves", barcode, "units"), "cursor" to cursor, "limit" to "50"), serializer())

    suspend fun unit(barcode: String): StockUnit = api.get(api.url(listOf("units", barcode)), serializer())

    suspend fun stock(productId: String): ProductStock =
        api.get(api.url(listOf("products", productId, "stock")), serializer())

    /** Scans carry the queued scan's key: a replay (offline queue, retry) returns the first result. */
    suspend fun stow(body: StowBody, key: String): StockUnit = scan("stow", body, StowBody.serializer(), key)

    suspend fun pick(body: PickBody, key: String): StockUnit = scan("pick", body, PickBody.serializer(), key)

    suspend fun relocate(body: RelocateBody, key: String): StockUnit = scan("relocate", body, RelocateBody.serializer(), key)

    suspend fun assign(body: AssignBody, key: String): StockUnit = scan("assign", body, AssignBody.serializer(), key)

    suspend fun unassign(body: UnassignBody, key: String): StockUnit = scan("unassign", body, UnassignBody.serializer(), key)

    private suspend fun <B> scan(op: String, body: B, s: KSerializer<B>, key: String): StockUnit =
        api.post(api.url(op), body, s, StockUnit.serializer(), mapOf("Idempotency-Key" to key))

}
