// SPDX-License-Identifier: Apache-2.0
package example.orders;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate sql;
    @BeforeEach void emptyOwnedFixture() {
        sql.execute("TRUNCATE TABLE orders RESTART IDENTITY");
    }
    @Test void persistsExactDecimalAndDeletes() throws Exception {
        mvc.perform(post("/orders/new").contentType("application/json")
            .content("{\"name\":\"Invoice\",\"amount\":\"999999999999.99\",\"note\":null}"))
            .andExpect(status().isCreated()).andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.amount").value("999999999999.99"));
        assertEquals("999999999999.99", sql.queryForObject("SELECT amount::text FROM orders", String.class));
        mvc.perform(delete("/orders/1")).andExpect(status().isNoContent()).andExpect(content().string(""));
        mvc.perform(get("/orders/1")).andExpect(status().isNotFound()).andExpect(jsonPath("$.code").value("not_found"));
    }
    @Test void validationDoesNotWrite() throws Exception {
        mvc.perform(post("/orders/new").contentType("application/json")
            .content("{\"name\":\" \",\"amount\":\"1.00\"}"))
            .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("invalid_request"));
        assertEquals(0, sql.queryForObject("SELECT count(*) FROM orders", Integer.class));
    }
    @Test void rollbackRemovesRowButConsumesIdentity() throws Exception {
        mvc.perform(post("/orders/rollback").contentType("application/json")
            .content("{\"name\":\"Rejected\",\"amount\":\"1.00\"}"))
            .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("rejected_write"));
        assertEquals(0, sql.queryForObject("SELECT count(*) FROM orders", Integer.class));
        mvc.perform(post("/orders/new").contentType("application/json")
            .content("{\"name\":\"Accepted\",\"amount\":\"2.00\"}"))
            .andExpect(status().isCreated()).andExpect(jsonPath("$.id").value(2));
    }
}
