// SPDX-License-Identifier: Apache-2.0
package example.greetings;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {
    @Autowired MockMvc mvc;
    @Test void defaultsAndLargeIntegers() throws Exception {
        mvc.perform(get("/api/greetings"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello, world"))
            .andExpect(jsonPath("$.requestId").value(9007199254740993L));
    }
    @Test void repeatedParameters() throws Exception {
        mvc.perform(get("/api/greetings").param("name", "Alice", "Bob"))
            .andExpect(jsonPath("$.message").value("Hello, Alice,Bob"));
    }
    @Test void unicodePath() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "世界"))
            .andExpect(jsonPath("$.message").value("Hello, 世界"));
    }
}
