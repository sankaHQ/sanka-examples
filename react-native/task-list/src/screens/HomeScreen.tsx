import React, { useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { RootStackParamList } from "../../App";

type Props = NativeStackScreenProps<RootStackParamList, "Home">;
type Task = { id: number; title: string; done: boolean };

export default function HomeScreen({ navigation }: Props) {
  const [title, setTitle] = useState("");
  const [tasks, setTasks] = useState<Task[]>([{ id: 1, title: "Read migration guide", done: false }]);
  return (
    <View style={styles.container}>
      <Text>Tasks ({tasks.length})</Text>
      <TextInput value={title} onChangeText={setTitle} placeholder="New task" />
      <Pressable onPress={() => {
        setTasks([...tasks, { id: tasks.length + 1, title, done: false }]);
        setTitle("");
      }}>
        <Text>Add task</Text>
      </Pressable>
      <FlatList
        data={tasks}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => (
          <Pressable onPress={() => navigation.navigate("Detail", { id: item.id, title: item.title })}>
            <Text>{item.title}</Text>
          </Pressable>
        )}
      />
    </View>
  );
}
const styles = StyleSheet.create({ container: { flex: 1, padding: 24, gap: 12 } });
