package bb.edu.cimh.sia.ui.nav

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AddBox
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Warehouse
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Outbox
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.navArgument
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import bb.edu.cimh.sia.AppContainer
import bb.edu.cimh.sia.data.Account
import bb.edu.cimh.sia.data.queue.ScanStatus
import bb.edu.cimh.sia.ui.create.CreateLocationScreen
import bb.edu.cimh.sia.ui.create.CreateLocationViewModel
import bb.edu.cimh.sia.ui.create.CreateProductScreen
import bb.edu.cimh.sia.ui.create.CreateProductViewModel
import bb.edu.cimh.sia.ui.home.HomeScreen
import bb.edu.cimh.sia.ui.lookup.LookupScreen
import bb.edu.cimh.sia.ui.lookup.LookupViewModel
import bb.edu.cimh.sia.ui.orders.OrdersScreen
import bb.edu.cimh.sia.ui.orders.OrdersViewModel
import bb.edu.cimh.sia.ui.orders.PickOrderScreen
import bb.edu.cimh.sia.ui.orders.PickOrderViewModel
import bb.edu.cimh.sia.ui.orders.ShipScreen
import bb.edu.cimh.sia.ui.pick.PickScreen
import bb.edu.cimh.sia.ui.pick.PickViewModel
import bb.edu.cimh.sia.ui.stow.StowScreen
import bb.edu.cimh.sia.ui.stow.StowViewModel
import bb.edu.cimh.sia.ui.sync.SyncScreen
import kotlinx.coroutines.launch

/** Bottom navigation (APD §5): Home · Lookup · Stow · Pick · Orders. */
enum class Tab(val route: String, val label: String, val hint: String, val icon: ImageVector) {
    Home("home", "Home", "", Icons.Filled.Home),
    Lookup("lookup", "Lookup", "Scan a shelf or unit, or search products", Icons.Filled.Search),
    Stow("stow", "Stow", "Scan a shelf, then the units going on it", Icons.Filled.Inventory2),
    Pick("pick", "Pick", "Take units off with a reason; issue to a person; returns", Icons.Filled.Outbox),
    Orders("orders", "Orders", "Requests to pick and ship", Icons.Filled.LocalShipping),
}

private const val SYNC = "sync"
private const val CREATE_PRODUCT = "create/product"
private const val CREATE_LOCATION = "create/location"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SiaApp(container: AppContainer, account: Account, onLogout: () -> Unit) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route
    val scans by container.scans.observe(account.id).collectAsStateWithLifecycle(emptyList())
    val lastSync by container.scans.lastSync.collectAsStateWithLifecycle()
    val pending = scans.count { it.status == ScanStatus.PENDING }
    val failed = scans.count { it.status == ScanStatus.FAILED }
    var menu by remember { mutableStateOf(false) }
    var confirmLogout by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    val open: (String) -> Unit = { r ->
        nav.navigate(r) {
            popUpTo(nav.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        when (route) {
                            SYNC -> "Sync queue"
                            CREATE_PRODUCT -> "Create product"
                            CREATE_LOCATION -> "Create location"
                            "orders/{id}/pick" -> "Pick order"
                            "orders/{id}/ship" -> "Ship"
                            else -> Tab.entries.firstOrNull { it.route == route?.substringBefore("?") }?.label ?: "SIA Mobile"
                        },
                    )
                },
                actions = {
                    IconButton(onClick = { menu = true }) {
                        BadgedBox(badge = { if (pending + failed > 0) Badge { Text("${pending + failed}") } }) {
                            Icon(Icons.Filled.MoreVert, contentDescription = "More")
                        }
                    }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(
                            text = { Text("Create product") },
                            leadingIcon = { Icon(Icons.Filled.AddBox, contentDescription = null) },
                            onClick = { menu = false; nav.navigate(CREATE_PRODUCT) },
                        )
                        DropdownMenuItem(
                            text = { Text("Create location") },
                            leadingIcon = { Icon(Icons.Filled.Warehouse, contentDescription = null) },
                            onClick = { menu = false; nav.navigate(CREATE_LOCATION) },
                        )
                        DropdownMenuItem(
                            text = { Text(if (pending + failed > 0) "Sync queue (${pending + failed})" else "Sync queue") },
                            leadingIcon = { Icon(Icons.Filled.Sync, contentDescription = null) },
                            onClick = { menu = false; open(SYNC) },
                        )
                        DropdownMenuItem(
                            text = { Text("Log out") },
                            leadingIcon = { Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null) },
                            onClick = {
                                menu = false
                                if (pending + failed > 0) confirmLogout = true else onLogout()
                            },
                        )
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = route?.substringBefore("?") == tab.route || (tab == Tab.Orders && route?.startsWith("orders/") == true),
                        onClick = { open(tab.route) },
                        icon = {
                            if (tab == Tab.Home && pending + failed > 0) {
                                BadgedBox(badge = { Badge { Text("${pending + failed}") } }) { Icon(tab.icon, contentDescription = null) }
                            } else {
                                Icon(tab.icon, contentDescription = null)
                            }
                        },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            nav,
            startDestination = Tab.Home.route,
            // Edge to edge: the keyboard does not resize the window, so the content makes room for it (scan fields stay visible).
            modifier = Modifier.padding(padding).consumeWindowInsets(padding).imePadding(),
        ) {
            composable(Tab.Home.route) {
                HomeScreen(account, pending, failed, lastSync, onOpen = { open(it.route) }, onSync = { open(SYNC) })
            }
            composable(
                "${Tab.Lookup.route}?product={product}",
                arguments = listOf(navArgument("product") { type = NavType.StringType; nullable = true; defaultValue = null }),
            ) { e ->
                LookupScreen(
                    viewModel { LookupViewModel(container.inventory, container.catalog, container.scans) },
                    openProduct = e.arguments?.getString("product"),
                )
            }
            composable(CREATE_PRODUCT) {
                CreateProductScreen(viewModel { CreateProductViewModel(container.catalog) }, onSaved = { id ->
                    nav.navigate("${Tab.Lookup.route}?product=$id") { popUpTo(CREATE_PRODUCT) { inclusive = true } }
                })
            }
            composable(CREATE_LOCATION) { CreateLocationScreen(viewModel { CreateLocationViewModel(container.inventory) }) }
            composable(Tab.Stow.route) {
                StowScreen(viewModel { StowViewModel(container.inventory, container.scans) }, onDone = { open(Tab.Home.route) })
            }
            composable(Tab.Pick.route) { PickScreen(viewModel { PickViewModel(container.scans, container.identity) }) }
            composable(Tab.Orders.route) {
                OrdersScreen(viewModel { OrdersViewModel(container.orders) }, onOpen = { id -> nav.navigate("orders/$id/pick") })
            }
            composable("orders/{id}/pick") { e ->
                val id = e.arguments?.getString("id").orEmpty()
                PickOrderScreen(
                    viewModel { PickOrderViewModel(container.orders, container.scans) },
                    requestId = id,
                    onShip = { nav.navigate("orders/$id/ship") },
                )
            }
            composable("orders/{id}/ship") { e ->
                ShipScreen(container.orders, e.arguments?.getString("id").orEmpty(), onShipped = {
                    nav.popBackStack(Tab.Orders.route, inclusive = false)
                })
            }
            composable(SYNC) { SyncScreen(container.scans, account.id) }
        }
    }

    if (confirmLogout) {
        AlertDialog(
            onDismissRequest = { confirmLogout = false },
            title = { Text("Scans not sent") },
            text = {
                Text(
                    "${pending + failed} scan${if (pending + failed == 1) " has" else "s have"} not reached the server. " +
                        "Logging out deletes them from this phone.",
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmLogout = false
                    scope.launch {
                        container.scans.clear()
                        onLogout()
                    }
                }) { Text("Delete and log out") }
            },
            dismissButton = { TextButton(onClick = { confirmLogout = false; open(SYNC) }) { Text("Open sync queue") } },
        )
    }
}
