import React, { useState } from "react";
import { Pressable, StyleSheet, Switch, Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { RootStackParamList } from "../../App";

type Props = NativeStackScreenProps<RootStackParamList, "Detail">;

export default function DetailScreen({ route, navigation }: Props) {
  const [done, setDone] = useState(false);
  return (
    <View style={styles.container}>
      <Text>{route.params.title}</Text>
      <Text>Task #{route.params.id}</Text>
      <Switch value={done} onValueChange={setDone} />
      <Text>{done ? "Completed" : "Open"}</Text>
      <Pressable onPress={() => navigation.goBack()}><Text>Back</Text></Pressable>
    </View>
  );
}
const styles = StyleSheet.create({ container: { flex: 1, padding: 24, gap: 12 } });
