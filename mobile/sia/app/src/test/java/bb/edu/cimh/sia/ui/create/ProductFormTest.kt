package bb.edu.cimh.sia.ui.create

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProductFormTest {
    private val ok = ProductForm(name = " Anemometer ", type = "MET", department = "Meteorology")

    @Test fun requiredFieldsAreChecked() {
        assertEquals(setOf("name", "type", "department"), ProductForm().errors().keys)
        assertTrue(ok.errors().isEmpty())
    }

    @Test fun costBecomesMoneyWithTwoDecimals() {
        assertEquals("249.50", ok.copy(cost = "249.5").toInput().cost)
        assertEquals("150.00", ok.copy(cost = "150").toInput().cost)
        assertEquals("cost", ok.copy(cost = "1,5").errors().keys.single())
        assertNull(ok.toInput().cost)
    }

    @Test fun proBonoIsAlwaysSellable() {
        val input = ok.copy(probono = true, sellable = false).toInput()
        assertTrue(input.sellable && input.probono)
    }

    @Test fun blanksAreNullAndDimensionsJoin() {
        val input = ok.copy(make = "  ", length = "10", height = "5").toInput()
        assertEquals("Anemometer", input.name)
        assertNull(input.make)
        assertEquals("10 x ? x 5", input.dimension)
        assertNull(ok.toInput().dimension)
    }
}
